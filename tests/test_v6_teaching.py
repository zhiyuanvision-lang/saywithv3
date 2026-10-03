import asyncio
import hashlib
import io
import wave
import copy
from test_backend import application,client,register,session,send

def upload(client,headers):
    b=io.BytesIO()
    with wave.open(b,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x01\0'*16000)
    r=client.post('/v1/media',headers=headers,files={'audio':('shadow.wav',b.getvalue(),'audio/wav')})
    assert r.status_code==201
    return r.json()['audio_ref']

def shadow(client,headers,s):
    url='/v1/sessions/'+s['view']['session_id']+'/shadow'
    body={'material_index':0,'audio_ref':upload(client,headers),'input_id':'shadow-one'}
    r=client.post(url,headers=headers,json=body);assert r.status_code==200,r.text
    assert r.json()['feedback']['can_continue']
    repeat=client.post(url,headers=headers,json=body);assert repeat.json()['feedback']==r.json()['feedback']
    return r.json()['session']

def next_round(client,headers,s):
    r=client.post('/v1/sessions/'+s['view']['session_id']+'/next',headers=headers,
                  json={'expected_session_version':s['session_version'],'advance_round':True})
    assert r.status_code==200,r.text
    return r.json()

def test_shadow_three_guided_rounds_and_feedback_without_mastery(client,application):
    h,user=register(client);s=session(client,application,h);id=s['view']['session_id']
    r=client.post('/v1/sessions/'+id+'/next',headers=h,json={'expected_session_version':s['session_version'],'advance_round':True})
    assert r.status_code==409
    s=shadow(client,h,s);assert s['view']['completed_material_indices']==[0]
    s=next_round(client,h,s)
    for i in range(3):
        assert s['view']['guided_round']==i+1
        assert not any(k in str(s) for k in ('partner_private_facts','assessment_contract'))
        assert send(client,h,s,text='How about three?',input_id='round'+str(i)).status_code==200
        s=client.get('/v1/sessions/'+id,headers=h).json();s=next_round(client,h,s)
    assert s['view']['phase']=='guided_feedback'
    s=next_round(client,h,s);assert s['view']['phase']=='independent_application'
    assert 'request_hint' not in s['view']['available_actions'] and not s['view']['materials']
    assert send(client,h,s,input_id='independent-v6').status_code==200
    result=client.post('/v1/sessions/'+id+'/finish',headers=h);assert result.status_code==200
    view=client.get('/v1/sessions/'+id,headers=h).json()
    assert view['view']['assessment']['validation']['status']=='rejected'
    assert client.get('/v1/profile',headers=h).json()['target_states']==[]

def test_hints_levels_are_recorded_without_partner_turns(client,application):
    h,user=register(client);s=shadow(client,h,session(client,application,h));s=next_round(client,h,s);id=s['view']['session_id']
    old=s['turns']
    for level,label in [('intent','意图提示'),('pattern','句型提示'),('example','完整示例'),('learned','所学表达')]:
        body={'session_id':id,'task_id':s['view']['task_id'],'input_id':'hint-'+level,'type':'request_hint','hint_level':level,
              'recorded_at':'2026-10-03T12:00:00Z','expected_session_version':s['session_version']}
        r=client.post('/v1/sessions/'+id+'/inputs',headers=h,json=body)
        assert r.status_code==200 and r.json()['support_provided']==[label]
        s=client.get('/v1/sessions/'+id,headers=h).json()
        assert s['turns']==old and label in s['view']['support_used']

def test_independent_policy_and_return_to_guidance_abandons_without_failure(client,application):
    h,user=register(client);s=session(client,application,h);id=s['view']['session_id'];svc=application.state.services
    row=svc.store.get('Session',id,user);p=row['payload'];p['phase']='independent_application'
    lesson=svc.store.get('LessonPackage',s['view']['lesson_id'],user)['payload'];p['task']=copy.deepcopy(lesson['independent_task'])
    p['task']['interaction_policy']={'show_text':False,'text_input':False,'request_repeat':False,'request_translation':False}
    p['turns']=[{'turn_id':'partner','speaker':'partner','text':'Hidden transcript','audio_ref':None}]
    svc.store.put('Session',id,user,p,expected=row['version'])
    s=client.get('/v1/sessions/'+id,headers=h).json()
    assert 'text' not in s['turns'][0] and 'text_input' not in s['view']['available_actions']
    for kind in ['text','request_hint','request_repeat','request_translation']:
        assert send(client,h,s,kind=kind,input_id=kind).status_code==409
    r=client.post('/v1/sessions/'+id+'/transition',headers=h,json={'action':'return_guided','expected_session_version':s['session_version']})
    assert r.status_code==200 and r.json()['view']['phase']=='supported_practice'
    attempts=svc.store.list('TaskAttempt',user);assert attempts[-1]['payload']['status']=='abandoned'
    assert client.get('/v1/profile',headers=h).json()['target_states']==[]

def test_shadow_cannot_use_another_users_audio(client,application):
    h,_=register(client);other,_=register(client);s=session(client,application,h)
    r=client.post('/v1/sessions/'+s['view']['session_id']+'/shadow',headers=h,
        json={'material_index':0,'audio_ref':upload(client,other),'input_id':'foreign'})
    assert r.status_code==404

def test_unclear_shadow_keeps_learning_progress(client,application):
    from backend.providers import ReviewRequired
    h,_=register(client);s=session(client,application,h)
    provider=application.state.services.provider
    async def unclear(*args):raise ReviewRequired('ASR unclear')
    provider.fixture=False;provider.transcribe=unclear
    r=client.post('/v1/sessions/'+s['view']['session_id']+'/shadow',headers=h,
        json={'material_index':0,'audio_ref':upload(client,h),'input_id':'unclear'})
    assert r.status_code==200 and not r.json()['feedback']['can_continue']
    assert r.json()['session']['view']['completed_material_indices']==[]
    assert client.get('/v1/profile',headers=h).json()['target_states']==[]

def test_invalid_guided_draft_repairs_before_session_transition(client,application):
    h,user=register(client);s=shadow(client,h,session(client,application,h));svc=application.state.services
    original=svc.provider.guided;calls=[]
    async def guided(lesson,target,previous,feedback=None):
        calls.append(feedback)
        if len(calls)==1:return {'tasks':[]}
        return await original(lesson,target,previous,feedback)
    svc.provider.guided=guided
    result=next_round(client,h,s)
    assert result['view']['guided_round']==1 and len(calls)==2 and calls[1]['issues']
    assert len(svc.store.list('GuidedTaskReview',user))==1

def test_translation_requires_owned_visible_turn(client,application):
    h,_=register(client);s=next_round(client,h,shadow(client,h,session(client,application,h)))
    id=s['view']['session_id']
    body={'session_id':id,'task_id':s['view']['task_id'],'input_id':'translation',
          'type':'request_translation','source_turn_id':'foreign-turn','recorded_at':'2026-10-03T12:00:00Z',
          'expected_session_version':s['session_version']}
    assert client.post('/v1/sessions/'+id+'/inputs',headers=h,json=body).status_code==422
    body['source_turn_id']=s['turns'][0]['turn_id']
    r=client.post('/v1/sessions/'+id+'/inputs',headers=h,json=body)
    assert r.status_code==200 and r.json()['kind']=='translation'
    saved=client.get('/v1/sessions/'+id,headers=h).json()
    assert saved['turns']==s['turns'] and '查看翻译' in saved['view']['support_used']

def test_audio_only_repeat_does_not_return_hidden_transcript(client,application):
    h,user=register(client);s=session(client,application,h);id=s['view']['session_id'];svc=application.state.services
    row=svc.store.get('Session',id,user);p=row['payload'];p['phase']='independent_application'
    p['task']=copy.deepcopy(svc.store.get('LessonPackage',s['view']['lesson_id'],user)['payload']['independent_task'])
    p['task']['interaction_policy']={'show_text':False,'request_repeat':True}
    svc.store.put('Session',id,user,p,expected=row['version']);s=client.get('/v1/sessions/'+id,headers=h).json()
    r=send(client,h,s,kind='request_repeat',input_id='repeat-hidden')
    assert r.status_code==200 and r.json()['kind']=='repeat' and r.json()['text']=='' and r.json()['audio_ref']

def test_review_starts_with_new_independent_task_and_records_metadata(client,application):
    import time
    h,user=register(client);svc=application.state.services
    assert client.get('/v1/recommendations',headers=h).json()['recommended'] is None
    row=svc.store.get('LearnerProfile',user,user);p=row['payload']
    p['target_states']=[{'target_id':'ARRANGE.A2.s2','independent':'provisional','due_at':time.time()-10,
        'observations':[{'independent':True,'completed':True,'time':time.time()-8*86400,'attempt_id':'baseline'}]}]
    svc.store.put('LearnerProfile',user,user,p,expected=row['version'])
    recommendation=client.get('/v1/recommendations',headers=h).json()
    assert recommendation['due_count']==1 and recommendation['recommended']['minutes']==5
    r=client.post('/v1/course-generation-jobs',headers={**h,'Idempotency-Key':'review'},
        json={'target_id':'ARRANGE.A2.s2','entry_kind':'review','minutes':5})
    asyncio.run(svc.generator.run_one('review-worker'))
    job=client.get('/v1/course-generation-jobs/'+r.json()['job_id'],headers=h).json()
    s=client.post('/v1/sessions',headers=h,json={'lesson_id':job['result_lesson_id'],'entry_kind':'review'}).json()
    assert s['view']['phase']=='independent_application' and not s['view']['materials']
    assert s['view']['review_metadata']['baseline_attempt_id']=='baseline'
    assert s['view']['review_metadata']['actual_interval_seconds']>=8*86400
    assert 'request_hint' not in s['view']['available_actions']
    r=client.post('/v1/sessions/'+s['view']['session_id']+'/transition',headers=h,
                  json={'action':'return_guided','expected_session_version':s['session_version']})
    assert r.status_code==200
    abandoned=svc.store.list('TaskAttempt',user)[0]['payload']
    assert abandoned['status']=='abandoned' and abandoned['review_metadata']['purpose']=='retention'

def test_review_after_abandonment_changes_previous_task_facts(client,application):
    import time
    h,user=register(client);svc=application.state.services;s=session(client,application,h)
    row=svc.store.get('LearnerProfile',user,user);p=row['payload'];p['target_states']=[{'target_id':'ARRANGE.A2.s2','independent':'supported','due_at':time.time()-1}]
    svc.store.put('LearnerProfile',user,user,p,expected=row['version'])
    old=svc.store.get('LessonPackage',s['view']['lesson_id'],user)['payload']['independent_task']
    svc.store.put('TaskSnapshot','abandoned/snapshot',user,old)
    svc.store.put('TaskAttempt','abandoned',user,{'attempt_id':'abandoned','target_ids':['ARRANGE.A2.s2'],'phase':'independent_application','status':'abandoned','task_snapshot_ref':'abandoned/snapshot','finished_at':'2026-10-03T12:00:00Z'})
    r=client.post('/v1/course-generation-jobs',headers={**h,'Idempotency-Key':'review-change'},json={'target_id':'ARRANGE.A2.s2','entry_kind':'review'})
    asyncio.run(svc.generator.run_one('review-worker'))
    job=client.get('/v1/course-generation-jobs/'+r.json()['job_id'],headers=h).json()
    assert job['result_lesson_id']
    lesson=svc.store.get('LessonPackage',job['result_lesson_id'],user)['payload']
    assert lesson['independent_task']['learner_facts']!=old['learner_facts']

def test_learned_exposure_is_reviewable_without_claiming_mastery(client,application):
    from datetime import datetime,timedelta,timezone
    h,owner=register(client);s=session(client,application,h)
    svc=application.state.services;row=svc.store.get('Session',s['view']['session_id'],owner);payload=row['payload']
    payload['learning_events']=[{'material_index':0,'personal_text':'How about four thirty?',
        'time':(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()}]
    svc.store.put('Session',row['id'],owner,payload,expected=row['version'])
    assert client.get('/v1/recommendations',headers=h).json()['learned']==[]  # fixture is excluded
    row=svc.store.get('Session',row['id'],owner);payload=row['payload'];payload['fixture']=False
    svc.store.put('Session',row['id'],owner,payload,expected=row['version'])
    data=client.get('/v1/recommendations',headers=h).json()
    assert data['recommended']['target_id']=='ARRANGE.A2.s2'
    assert data['learned'][0]['exposure_only'] and data['due_count']==1
    profile=client.get('/v1/profile',headers=h).json();assert profile['target_states']==[]
    assignment,_=svc.planner.plan(profile,{'target_id':data['recommended']['target_id'],'entry_kind':'review'})
    assert assignment['purpose']=='consolidation' and assignment['review_metadata']['baseline_attempt_id'] is None
    assert client.get('/v1/recommendations',headers=register(client)[0]).json()['learned']==[]

def test_home_recommendation_matches_scheduler_without_creating_records(client,application):
    h,_=register(client);p=client.get('/v1/profile',headers=h).json();svc=application.state.services
    before=len(svc.store.list('LearningPlan',p['user_id']))
    recommended=client.get('/v1/recommendations',headers=h).json()['next_learning']
    assert len(svc.store.list('LearningPlan',p['user_id']))==before
    assert svc.planner.plan(p,{})[0]['target_ids']==[recommended['target_id']]

def test_audio_clock_spellings_keep_critical_time_values():
    from backend.providers import audio_normalized
    assert audio_normalized("Does five o'clock work?")==audio_normalized('Does 05:00 work?')
    assert audio_normalized('How about four thirty?')==audio_normalized('How about 4:30?')
    assert audio_normalized("five o'clock")!=audio_normalized('5:30')
    assert audio_normalized("five o'clock")!=audio_normalized("four o'clock")
    assert audio_normalized("I can't do five o'clock")!=audio_normalized('I can do 5:00')

def test_invalid_generated_schema_is_repaired_without_accepting_extra_fields(application,client):
    svc=application.state.services;h,_=register(client)
    original=svc.provider.generate
    async def malformed(*args,**kwargs):
        result=await original(*args,**kwargs);result['type']='json_object';return result
    svc.provider.generate=malformed;svc.provider.fixture=False
    job=client.post('/v1/course-generation-jobs',headers={**h,'Idempotency-Key':'schema-repair'},json={'target_id':'ARRANGE.A2.s2'}).json()
    asyncio.run(svc.generator.run_one('repair-test'))
    row=svc.store.job(job['job_id'])
    assert row['state']=='generating_text'
    assert row['payload']['text_revisions']==1
    assert 'type' in row['payload']['repair_feedback']
    assert 'lesson' not in row['payload']

def test_spoken_clock_preserves_hour_minutes_and_meridiem():
    from backend.providers import spoken_clock,audio_normalized
    assert spoken_clock('At 18:00.')=='At 6:00 p.m.'
    assert spoken_clock('At 6:00 p.m.')=='At 6:00 p.m.'
    for original,transcript in [('18:00','six p.m.'),('00:00','twelve a.m.'),('12:30','twelve thirty p.m.'),('18:45','six forty five p.m.')]:
        assert audio_normalized(original)==audio_normalized(transcript)
    assert audio_normalized('18:00')!=audio_normalized("eight o'clock")
    assert audio_normalized('six a.m.')!=audio_normalized('six p.m.')

def test_learning_expression_cannot_be_a_placeholder_formula(client,application):
    from backend.generation import inspect_lesson
    h,_=register(client);s=session(client,application,h)
    svc=application.state.services
    lesson=svc.store.get('LessonPackage',s['view']['lesson_id'])['payload']
    with svc.store.engine.connect() as c:
        from sqlalchemy import select
        row=c.execute(select(svc.store.jobs.c.payload)).scalar_one()
    lesson['learning_materials'][0]['expression']='How about + time?'
    assert any('hint_pattern' in issue for issue in inspect_lesson(lesson,row['assignment'],row['target']))
