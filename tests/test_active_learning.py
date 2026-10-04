import copy
import time
import pytest
from test_backend import application,client,register,session,send
from test_v6_teaching import upload,next_round

def act(c,h,s,action,**extra):
    body={'material_index':0,'action':action,'expected_session_version':s['session_version'],**extra}
    r=c.post('/v1/sessions/'+s['view']['session_id']+'/learning-practice',headers=h,json=body)
    assert r.status_code==200,r.text
    return r.json()

def speak(c,h,s,key='one'):
    return act(c,h,s,'attempt',stage=s['view']['learning_practice']['stage'],input_id=key,audio_ref=upload(c,h))

def learned(c,app,h,direct=False):
    s=act(c,h,session(c,app,h),'prepare')
    if not direct:s=speak(c,h,act(c,h,s,'start'),'supported')
    s=act(c,h,s,'recall');s=speak(c,h,s,'recall')
    return s

def test_active_learning_to_guided_independent_feedback_and_repair_loop(client,application):
    h,user=register(client);s=learned(client,application,h)
    assert s['view']['completed_material_indices']==[0]
    assert client.get('/v1/profile',headers=h).json()['target_states']==[]
    s=next_round(client,h,s)
    assert s['view']['guided_round']==1 and s['view']['guided_round_total']==2
    for i in range(2):
        assert send(client,h,s,input_id='guided'+str(i)).status_code==200
        s=client.get('/v1/sessions/'+s['view']['session_id'],headers=h).json();s=next_round(client,h,s)
    assert s['view']['phase']=='guided_feedback'
    s=next_round(client,h,s);old_task=s['view']['task_id'];old_facts=s['view']['learner_facts']
    assert send(client,h,s,input_id='independent').status_code==200
    assert client.post('/v1/sessions/'+s['view']['session_id']+'/finish',headers=h).status_code==200
    s=client.get('/v1/sessions/'+s['view']['session_id'],headers=h).json()
    assert s['view']['feedback_turn_id']
    r=client.post('/v1/sessions/'+s['view']['session_id']+'/transition',headers=h,json={'action':'retry_guided','expected_session_version':s['session_version']})
    assert r.status_code==200,(r.text,[r['payload']['review'] for r in application.state.services.store.list('GuidedTaskReview',user)]);s=r.json()
    assert s['view']['guided_round_total']==1 and s['view']['guided_round']==1
    assert send(client,h,s,input_id='repair').status_code==200
    s=client.get('/v1/sessions/'+s['view']['session_id'],headers=h).json();s=next_round(client,h,s);s=next_round(client,h,s)
    assert s['view']['phase']=='independent_application' and s['view']['task_id']!=old_task
    assert s['view']['learner_facts']!=old_facts and 'request_hint' not in s['view']['available_actions']
    # Full original criteria and changed concrete conditions survive remediation.
    svc=application.state.services;state=svc.store.get('Session',s['view']['session_id'],user)['payload']
    original=svc.store.get('LessonPackage',s['view']['lesson_id'],user)['payload']['independent_task']
    assert state['task']['assessment_contract']['critical_checks']==original['assessment_contract']['critical_checks']

def test_direct_retrieval_and_no_legacy_shadow_bypass(client,application):
    h,user=register(client);s=act(client,h,session(client,application,h),'prepare')
    s=client.post('/v1/sessions/'+s['view']['session_id']+'/learn',headers=h,json={'material_index':0,'personal_text':'How about two?'}).json()
    assert client.post('/v1/sessions/'+s['view']['session_id']+'/next',headers=h,json={'expected_session_version':s['session_version']}).status_code==409
    s=act(client,h,s,'recall');assert not s['view']['learning_practice']['pattern']
    assert not s['view']['learning_practice'].get('example')
    s=speak(client,h,s);assert s['view']['learning_practice']['stage']=='complete'

def test_help_exposes_example_only_on_request_then_changes_retrieval_cue(client,application):
    h,_=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall')
    cue=s['view']['learning_practice']['prompt_zh']
    s=act(client,h,s,'show_example')
    assert s['view']['learning_practice']['example']['expression']
    assert s['view']['learning_practice']['stage']=='supported'
    s=speak(client,h,s);s=act(client,h,s,'recall')
    assert s['view']['learning_practice']['prompt_zh']!=cue
    assert not s['view']['learning_practice'].get('example') and not s['view']['learning_practice']['pattern']

@pytest.mark.parametrize('met,confidence,expected',[(False,'high','recall'),(True,'low','recall'),(True,'high','complete')])
def test_semantic_judgement_gates_progress_without_exact_match(client,application,met,confidence,expected):
    h,_=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall');provider=application.state.services.provider
    async def transcribe(*a):return {'text':'Could we meet at three?','quality':'final_transcript_available'}
    async def judge(m,p,t):
        assert t=='Could we meet at three?'
        return {'met':met,'confidence':confidence,'explanation_zh':'时间不对，试试 How about three?','better_expression':'How about three?','meaning_zh':'三点怎么样？'}
    provider.fixture=False;provider.transcribe=transcribe;provider.learning_judgement=judge
    s=speak(client,h,s)
    practice=s['view']['learning_practice'];assert practice['stage']==expected
    assert bool(practice['feedback']['better_expression'])==(expected=='complete')
    if expected=='recall':
        assert 'How' not in practice['feedback']['explanation_zh']
        assert s['view']['completed_material_indices']==[]
        s=act(client,h,s,'show_example');assert s['view']['learning_practice']['example']['expression']=='How about three?'

def test_learning_audio_ownership_stale_version_and_receipt_idempotency(client,application):
    h,_=register(client);other,_=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall')
    body={'material_index':0,'action':'attempt','stage':'recall','input_id':'repeat','audio_ref':upload(client,other),'expected_session_version':s['session_version']}
    url='/v1/sessions/'+s['view']['session_id']+'/learning-practice'
    assert client.post(url,headers=h,json=body).status_code==404
    body['audio_ref']=upload(client,h);body['expected_session_version']-=1
    assert client.post(url,headers=h,json=body).status_code==409
    body['expected_session_version']=s['session_version']
    a=client.post(url,headers=h,json=body);b=client.post(url,headers=h,json=body)
    assert a.status_code==b.status_code==200 and a.json()==b.json()
    body['audio_ref']=upload(client,h);assert client.post(url,headers=h,json=body).status_code==409

def test_retry_independent_makes_fresh_tasks_repeatedly(client,application):
    h,user=register(client);s=session(client,application,h);svc=application.state.services;id=s['view']['session_id']
    for i in range(3):
        row=svc.store.get('Session',id,user);p=row['payload'];old=copy.deepcopy(p['task']);p['phase']='finished'
        svc.store.put('Session',id,user,p,expected=row['version']);s=client.get('/v1/sessions/'+id,headers=h).json()
        r=client.post('/v1/sessions/'+id+'/transition',headers=h,json={'action':'retry_independent','expected_session_version':s['session_version']})
        assert r.status_code==200,(r.text,[r['payload']['review'] for r in application.state.services.store.list('GuidedTaskReview',user)]);s=r.json()
        assert s['view']['phase']=='independent_application' and s['view']['task_id']!=old['task_id']
        assert s['view']['learner_facts']!=old['learner_facts']

def test_clean_accepted_guidance_skips_duplicate_round(client,application):
    h,user=register(client);s=next_round(client,h,learned(client,application,h));svc=application.state.services
    assert send(client,h,s,input_id='clean').status_code==200
    async def assessed(*a,**k):return {'validation':{'status':'accepted'},'target_results':[{'result':'completed','confidence':'high'}]}
    svc.sessions.finish_attempt=assessed
    s=client.get('/v1/sessions/'+s['view']['session_id'],headers=h).json();s=next_round(client,h,s)
    assert s['view']['phase']=='guided_feedback'

def test_answer_help_blocks_early_skip(client,application):
    h,user=register(client);s=next_round(client,h,learned(client,application,h));svc=application.state.services
    assert send(client,h,s,input_id='helped').status_code==200
    row=svc.store.get('Session',s['view']['session_id'],user);p=row['payload'];p['support_used']=['回答示范'];svc.store.put('Session',row['id'],user,p,expected=row['version'])
    async def assessed(*a,**k):return {'validation':{'status':'accepted'},'target_results':[{'result':'completed','confidence':'high'}]}
    svc.sessions.finish_attempt=assessed
    s=client.get('/v1/sessions/'+s['view']['session_id'],headers=h).json();s=next_round(client,h,s)
    assert s['view']['phase']=='supported_practice' and s['view']['guided_round']==2

def test_unclear_asr_returns_retryable_feedback_not_mastery(client,application):
    from backend.providers import ReviewRequired
    h,_=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall')
    provider=application.state.services.provider
    async def unclear(*a):raise ReviewRequired('Cannot hear')
    provider.fixture=False;provider.transcribe=unclear
    s=speak(client,h,s)
    assert s['view']['learning_practice']['stage']=='recall'
    assert s['view']['learning_practice']['feedback']['confidence']=='low'
    assert s['view']['completed_material_indices']==[]

@pytest.mark.parametrize('supports,eligible,expected,recent',[([],True,'provisional',None),(['回答示范'],True,'supported',None),([],False,'provisional',None),([],True,'provisional',1)])
def test_validated_evidence_schedules_review_without_claiming_post_help_retention(client,application,supports,eligible,expected,recent):
    h,user=register(client);s=session(client,application,h);svc=application.state.services
    lesson=svc.store.get('LessonPackage',s['view']['lesson_id'],user)['payload'];task=lesson['independent_task']
    row=svc.store.get('LearnerProfile',user,user);p=row['payload'];p['target_states']=[{'target_id':'ARRANGE.A2.s2','independent':'insufficient_evidence','retention':'not_checked','transfer':'not_checked','support_dependency':[],'evidence_ids':[],'observations':[{'independent':True,'completed':True,'session_id':'baseline','attempt_id':'baseline','time':time.time()-10*86400,'scenario_signature':'old'}]}]
    if recent:p['target_states'][0]['observations'].append({'independent':True,'completed':True,'session_id':'recent','attempt_id':'recent','time':time.time()-recent*86400,'scenario_signature':'recent'})
    svc.store.put('LearnerProfile',user,user,p,expected=row['version'])
    attempt={'user_id':user,'target_ids':['ARRANGE.A2.s2'],'phase':'independent_application','support_used':supports,'review_metadata':{'retention_eligible':eligible},'attempt_id':'new-attempt','session_id':s['view']['session_id'],'lexical_resources':[],'task_snapshot_ref':'snapshot','map_version':lesson['map_version']}
    result={'evidence_ids':['real-evidence'],'assessment_id':'result','target_results':[{'result':'completed','confidence':'high'}]}
    # Baseline and current session count as two independent sessions only without answer help.
    with svc.store.transaction() as c:svc.assessor.update_profile(attempt,task,result,c)
    profile=client.get('/v1/profile',headers=h).json();state=profile['target_states'][0]
    assert state['independent']==('demonstrated' if not supports else expected)
    assert (state['retention']=='demonstrated')==(not supports and eligible and not recent)
    assert state['due_at']-time.time()>(6*86400 if not supports else 0)
    if supports:assert state['due_at']-time.time()<86401
    # Scheduler consumes the updated capability evidence.
    row=svc.store.get('LearnerProfile',user,user);p=row['payload'];p['target_states'][0]['due_at']=time.time()-1
    svc.store.put('LearnerProfile',user,user,p,expected=row['version'])
    recommendation=client.get('/v1/recommendations',headers=h).json()
    assert recommendation['due_count']==1 and recommendation['recommended']['target_id']=='ARRANGE.A2.s2'

def test_repeated_demonstration_condition_is_repaired_before_delivery(client,application):
    h,_=register(client);s=session(client,application,h);p=application.state.services.provider;calls=[]
    async def review(material,plan):
        calls.append(plan)
        return {'decision':'fail','reasons':['与示范条件重复']} if len(calls)==1 else {'decision':'pass'}
    p.review_learning_plan=review
    s=act(client,h,s,'prepare')
    assert len(calls)==2 and s['view']['learning_practice']['stage']=='preview'

def test_help_example_is_bound_to_the_current_retrieval_cue(client,application):
    h,_=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall')
    s=act(client,h,s,'show_example');first=s['view']['learning_practice']['example']['expression']
    s=speak(client,h,s);s=act(client,h,s,'recall');s=act(client,h,s,'show_example')
    assert s['view']['learning_practice']['example']['expression'] != first
    assert 'five' in s['view']['learning_practice']['example']['expression']


def test_mismatched_worked_example_is_repaired_before_display(client,application):
    h,_=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall')
    p=application.state.services.provider;calls=[]
    async def judge(m,prompt,transcript):
        calls.append(prompt)
        return {'met':False,'confidence':'high','explanation_zh':'示范',
                'better_expression':'I pack the books.' if len(calls)==1 else 'How about three?',
                'meaning_zh':'我打包书。' if len(calls)==1 else '三点怎么样？'}
    async def review(prompt,example):
        return {'decision':'fail','reasons':['示范说搬家，提示要求约时间']} if 'books' in example['expression'] else {'decision':'pass'}
    p.learning_judgement=judge;p.review_learning_example=review
    s=act(client,h,s,'show_example')
    assert len(calls)==2
    assert s['view']['learning_practice']['example']['expression']=='How about three?'

def test_old_unchecked_example_is_hidden_and_repaired_on_restore(client,application):
    h,user=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall');s=act(client,h,s,'show_example')
    svc=application.state.services;row=svc.store.get('Session',s['view']['session_id'],user);state=copy.deepcopy(row['payload'])
    practice=state['learning_practices']['0'];practice['recovery_example']={'expression':'I pack the books.','meaning_zh':'我打包书。'}
    practice.pop('recovery_example_prompt',None);practice.pop('checked_example_prompt',None)
    svc.store.put('Session',s['view']['session_id'],user,state,expected=row['version'])
    s=client.get('/v1/sessions/'+s['view']['session_id'],headers=h).json()
    assert s['view']['learning_practice']['example'] is None
    s=act(client,h,s,'prepare')
    assert s['view']['learning_practice']['example']['expression']=='How about three?'


def test_unrepairable_example_preserves_retrieval_progress(client,application):
    h,user=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall')
    async def reject(*args):return {'decision':'fail','reasons':['内容不对应']}
    application.state.services.provider.review_learning_example=reject
    result=client.post('/v1/sessions/'+s['view']['session_id']+'/learning-practice',headers=h,json={'material_index':0,'action':'show_example','expected_session_version':s['session_version']})
    assert result.status_code==422
    restored=client.get('/v1/sessions/'+s['view']['session_id'],headers=h).json()
    assert restored['session_version']==s['session_version']
    assert restored['view']['learning_practice']['stage']=='recall'
    assert not restored['view']['learning_practice'].get('example')

def test_learning_transcript_is_available_before_judgement(client,application):
    h,user=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall');svc=application.state.services;p=svc.provider
    async def transcribe(*args):return {'text':'Could we meet at three?','quality':'final_transcript_available'}
    async def judge(*args):
        progress=svc.sessions.input_progress(s['view']['session_id'],user,'early-text')
        assert progress['status']=='responding' and progress['transcript']=='Could we meet at three?'
        return {'met':False,'confidence':'high','explanation_zh':'时间不对，试试 How about three?','reason_zh':'识别出的时间与要求不一致。'}
    p.fixture=False;p.transcribe=transcribe;p.learning_judgement=judge
    s=speak(client,h,s,key='early-text')
    assert s['view']['learning_practice']['feedback']['explanation_zh']=='识别出的时间与要求不一致。'

def test_recheck_reuses_owned_audio_and_gets_a_fresh_transcript(client,application):
    h,_=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall');p=application.state.services.provider;calls=[]
    async def plain(*args):calls.append('plain');return {'text':'wrong','quality':'final_transcript_available'}
    async def contextual(*args):calls.append('context');return {'text':'correct','quality':'final_transcript_available'}
    async def judge(m,c,t):return {'met':t=='correct','confidence':'high','explanation_zh':'表达不符合当前要求。' if t=='wrong' else '表达清楚。'}
    p.fixture=False;p.transcribe=plain;p.transcribe_learning=contextual;p.learning_judgement=judge
    s=speak(client,h,s);ref=s['view']['learning_practice']['feedback']['audio_ref']
    s=act(client,h,s,'attempt',stage='recall',input_id='recheck',audio_ref=ref,recognition_retry=True)
    assert calls==['plain','context']
    assert s['view']['learning_practice']['feedback']['audio_ref']==ref
    assert s['view']['learning_practice']['feedback']['transcript']=='correct'
    assert s['view']['learning_practice']['stage']=='complete'


def test_confirmed_transcript_reuses_recording_and_keeps_raw_evidence(client,application):
    h,user=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall');p=application.state.services.provider;calls=[]
    async def transcribe(*args):calls.append('asr');return {'text':'Unpack the books.','quality':'final_transcript_available'}
    async def judge(m,c,t):return {'met':t=='I pack the books.','confidence':'high','explanation_zh':'已确认。'}
    p.fixture=False;p.transcribe=transcribe;p.learning_judgement=judge
    s=speak(client,h,s,key='raw');f=s['view']['learning_practice']['feedback'];ref=f['audio_ref']
    s=act(client,h,s,'attempt',stage='recall',input_id='confirmed',audio_ref=ref,confirmed_transcript='I pack the books.',original_transcript=f['transcript'])
    assert calls==['asr']
    assert s['view']['learning_practice']['stage']=='complete'
    assert s['view']['learning_practice']['feedback']['transcript_source']=='learner_confirmed'
    row=application.state.services.store.get('LearningPracticeAttempt',s['view']['session_id']+'/confirmed',user)['payload']
    assert row['feedback']['original_transcript']=='Unpack the books.'
    assert row['feedback']['audio_ref']==ref
    assert application.state.services.store.get('LearningPracticeAttempt',s['view']['session_id']+'/raw',user)['payload']['feedback']['transcript']=='Unpack the books.'


def test_confirmation_requires_current_recording_and_original_text(client,application):
    h,_=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall');p=application.state.services.provider;p.fixture=False
    async def transcribe(*args):return {'text':'Unpack the books.','quality':'final_transcript_available'}
    async def judge(*args):return {'met':False,'confidence':'high','explanation_zh':'请确认识别文字。'}
    p.transcribe=transcribe;p.learning_judgement=judge;s=speak(client,h,s)
    result=client.post('/v1/sessions/'+s['view']['session_id']+'/learning-practice',headers=h,json={'material_index':0,'action':'attempt','stage':'recall','input_id':'invalid-correction','audio_ref':upload(client,h),'confirmed_transcript':'I pack the books.','original_transcript':'different','expected_session_version':s['session_version']})
    assert result.status_code==409 and '录音或识别文字已更新' in result.text


def test_ambiguous_pack_recording_is_not_judged_as_wrong(client,application):
    h,user=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall');svc=application.state.services
    state=svc.store.get('Session',s['view']['session_id'],user)['payload'];row=svc.store.get('LessonPackage',state['lesson_id'],user)
    lesson=copy.deepcopy(row['payload']);lesson['learning_materials'][0]['expression']='Let me check: I pack the kitchen stuff, and you pack the books?'
    svc.store.put('LessonPackage',state['lesson_id'],user,lesson,expected=row['version'])
    p=svc.provider;p.fixture=False
    async def transcribe(*args):return {'text':'Let me check. Unpack the kitchen stocks, and you pack these books.','quality':'final_transcript_available'}
    async def judge(*args):raise AssertionError('Ambiguous ASR must not be graded as learner speech')
    p.transcribe=transcribe;p.learning_judgement=judge
    s=speak(client,h,s);f=s['view']['learning_practice']['feedback']
    assert not f['met'] and f['confidence']=='low'
    assert '识别存在歧义' in f['explanation_zh'] and '暂不判断' in f['explanation_zh']
    assert f['transcript'].startswith('Let me check. Unpack')

@pytest.mark.parametrize('met,confidence,next_stage',[(True,'high','recall'),(False,'high','supported'),(True,'low','supported')])
def test_supported_success_auto_advances_and_preserves_feedback(client,application,met,confidence,next_stage):
    h,_=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'start')
    original_cue=s['view']['learning_practice']['prompt_zh']
    provider=application.state.services.provider;provider.fixture=False
    async def transcribe(*args):return {'text':'How about three?','quality':'final_transcript_available'}
    async def judge(*args):return {'met':met,'confidence':confidence,'explanation_zh':'表达清楚。' if met else '时间不符合要求。'}
    provider.transcribe=transcribe;provider.learning_judgement=judge
    s=speak(client,h,s,'auto-transition');practice=s['view']['learning_practice']
    assert practice['stage']==next_stage
    if next_stage=='recall':
        assert practice['previous_feedback']['met']
        assert practice['feedback'] is None
        assert practice['prompt_zh']!=original_cue
        assert not practice['pattern'] and not practice.get('example')
        restored=client.get('/v1/sessions/'+s['view']['session_id'],headers=h).json()
        assert restored['view']['learning_practice']['previous_feedback']==practice['previous_feedback']
    else:assert practice['feedback'] and not practice.get('previous_feedback')

def test_prepare_advances_previously_passed_supported_practice(client,application):
    h,user=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'start')
    svc=application.state.services;row=svc.store.get('Session',s['view']['session_id'],user);state=copy.deepcopy(row['payload'])
    practice=state['learning_practices']['0']
    feedback={'met':True,'confidence':'high','explanation_zh':'表达清楚。','transcript':'How about three?','audio_ref':'/v1/media/test','fixture':True,'better_expression':'','meaning_zh':''}
    practice['feedback']=feedback
    svc.store.put('Session',s['view']['session_id'],user,state,expected=row['version'])
    s=client.get('/v1/sessions/'+s['view']['session_id'],headers=h).json()
    s=act(client,h,s,'prepare');assert s['view']['learning_practice']['stage']=='recall'
    assert s['view']['learning_practice']['previous_feedback']==feedback
    restored=act(client,h,s,'prepare');assert restored['session_version']==s['session_version']

def test_successful_retrieval_preserves_corrected_sentence_without_rewriting_transcript(client,application):
    h,_=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall')
    provider=application.state.services.provider;provider.fixture=False
    raw='Where should we meet for preparing our friends? Birthday.'
    corrected="Where should we meet to prepare for our friend's birthday?"
    async def transcribe(*args):return {'text':raw,'quality':'final_transcript_available'}
    async def judge(*args):return {'met':True,'confidence':'high','explanation_zh':'意思表达清楚，句子还可以调整。','better_expression':corrected,'meaning_zh':'我们应该在哪里见面，为朋友的生日做准备？'}
    provider.transcribe=transcribe;provider.learning_judgement=judge
    s=speak(client,h,s,'correct-after-success');p=s['view']['learning_practice']
    assert p['stage']=='complete' and p['feedback']['met']
    assert p['feedback']['transcript']==raw
    assert p['feedback']['better_expression']==corrected
    assert p['feedback']['meaning_zh']


def test_vague_cue_is_repaired_and_three_clear_cues_are_delivered(client,application):
    h,_=register(client);s=session(client,application,h);p=application.state.services.provider
    original=p.learning_plan;calls=[]
    async def generate(material,feedback=None):
        calls.append(feedback)
        plan=await original(material,feedback)
        if len(calls)==1:plan['recall_prompts_zh'][0]='下个月聚会，确认你和朋友各自要准备的节目。'
        return plan
    p.learning_plan=generate
    s=act(client,h,s,'prepare')
    assert len(calls)==2 and '情境' in calls[1]
    s=act(client,h,s,'recall');cue=s['view']['learning_practice']['prompt_zh']
    assert cue.startswith('情境：') and '\n轮到你：' in cue


def test_pattern_help_never_silently_reveals_example_and_next_cue_changes(client,application):
    h,_=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall')
    cue=s['view']['learning_practice']['prompt_zh'];s=act(client,h,s,'show_pattern')
    assert s['view']['learning_practice']['pattern'] and not s['view']['learning_practice'].get('example')
    s=act(client,h,s,'prepare')
    assert s['view']['learning_practice']['prompt_zh']==cue
    assert not s['view']['learning_practice'].get('example')
    s=act(client,h,s,'show_example');assert s['view']['learning_practice']['example']['expression']
    s=speak(client,h,s);assert s['view']['learning_practice']['stage']=='recall'
    assert s['view']['learning_practice']['prompt_zh']!=cue
    assert not s['view']['learning_practice']['pattern']


def test_unanswered_old_recall_task_refreshes_without_resetting_stage(client,application):
    h,user=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall')
    store=application.state.services.store;id=s['view']['session_id'];row=store.get('Session',id,user)
    state=copy.deepcopy(row['payload']);practice=state['learning_practices']['0']
    practice['plan_version']=3;practice['recall_prompts_zh']=['确认各自节目。','确认各自安排。']
    store.put('Session',id,user,state,expected=row['version'])
    s=client.get('/v1/sessions/'+id,headers=h).json();s=act(client,h,s,'prepare')
    assert s['view']['learning_practice']['stage']=='recall'
    assert s['view']['learning_practice']['prompt_zh'].startswith('情境：')

def test_completed_legacy_feedback_gets_correct_sentence_without_regrading(client,application):
    h,user=register(client);s=act(client,h,session(client,application,h),'prepare');s=act(client,h,s,'recall')
    s=speak(client,h,s,'completed-legacy');svc=application.state.services
    row=svc.store.get('Session',s['view']['session_id'],user);state=copy.deepcopy(row['payload'])
    feedback=state['learning_practices']['0']['feedback'];feedback.update(fixture=False,transcript='Where should we meet for preparing our friends? Birthday.',better_expression='',meaning_zh='')
    original=copy.deepcopy(feedback)
    svc.store.put('Session',s['view']['session_id'],user,state,expected=row['version'])
    s=client.get('/v1/sessions/'+s['view']['session_id'],headers=h).json();calls=[]
    async def judge(material,prompt,transcript):
        calls.append(transcript)
        return {'met':False,'confidence':'low','explanation_zh':'新评判不覆盖旧结果。','better_expression':"Where should we meet to prepare for our friend's birthday?",'meaning_zh':'我们应该在哪里见面，为朋友的生日做准备？'}
    svc.provider.learning_judgement=judge
    s=act(client,h,s,'prepare');f=s['view']['learning_practice']['feedback']
    assert f['better_expression'] and f['meaning_zh']
    assert all(f[k]==original[k] for k in ['met','confidence','explanation_zh','transcript','audio_ref'])
    assert s['view']['learning_practice']['stage']=='complete'
    act(client,h,s,'prepare');assert len(calls)==1
