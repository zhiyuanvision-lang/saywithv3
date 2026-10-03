import asyncio
import copy
import hashlib
import time
import pytest
from test_backend import application,client,register,generate
from backend.lexical import select_words,validate_checks,apply_checks
from backend.generation import inspect_lesson
from backend.store import Missing


def setup_word(client,application):
    h,user=register(client)
    saved=client.post('/v1/notebook',headers=h,json={'word':'available','context':'Are you available tomorrow?'}).json()
    job=generate(client,application,h)
    s=client.post('/v1/sessions',headers=h,json={'lesson_id':job['result_lesson_id']}).json()
    svc=application.state.services;lesson=svc.store.get('LessonPackage',job['result_lesson_id'],user)['payload']
    resource=svc.store.get('TeachingAssignment',lesson['assignment_id'],user)['payload']['resource_plan']['notebook_words'][0]
    return h,user,s,lesson,resource,saved


def check(r,result='correct_usage',turn_id='learner',quote='I am available tomorrow.'):
    return {'checks':[{'resource_id':r['resource_id'],'sense_id':r['sense_id'],'result':result,'confidence':'high','evidence_refs':[turn_id],'quote':quote}]}


def test_bounded_relevant_sense_selection_and_contracts(client,application):
    from backend.contracts import NotebookEntry,LexicalPracticeInput,TaskAttempt
    h,user,s,lesson,r,saved=setup_word(client,application)
    NotebookEntry.model_validate(saved)
    assert '有空' in r['meaning_zh'] and r['resource_id']=='lexeme:available'
    assert len(lesson['lexical_practices'])==1
    assert not s['view']['lexical_practices'][0]['completed']
    assert 'example' not in s['view']['lexical_practices'][0]
    assert s['view']['materials']==[] and s['view']['demonstration']==[]
    assert 'available' not in s['view']['lexical_practices'][0]['prompt_zh'].lower()
    profile=client.get('/v1/profile',headers=h).json();t=application.state.services.curriculum.target('ARRANGE.A2.s2')
    entries=[saved]
    for i in range(20):
        e=copy.deepcopy(saved);e.update(word='available'+str(i),id=str(i));entries.append(e)
        profile['resource_states'].append({'resource_id':'lexeme:'+e['word'],'notebook_active':True})
    assert len(select_words(profile,t,entries))<=2
    unrelated=copy.deepcopy(saved);unrelated.update(word='astronomy',id='other',contexts=[]);unrelated['card']={'senses':[{'meaning_en':'study of stars and galaxies','meaning_cn':'天文学'}]}
    profile['resource_states'].append({'resource_id':'lexeme:astronomy','notebook_active':True})
    assert select_words(profile,t,[unrelated])==[]
    assert inspect_lesson(lesson,application.state.services.store.get('TeachingAssignment',lesson['assignment_id'],user)['payload'],t)==[]
    bad=copy.deepcopy(lesson);bad['lexical_practices'][0]['sense_id']='fabricated'
    assert inspect_lesson(bad,application.state.services.store.get('TeachingAssignment',lesson['assignment_id'],user)['payload'],t)


def test_quote_refs_forms_and_paraphrase_are_conservative(client,application):
    h,user,s,lesson,r,_=setup_word(client,application)
    turns=[{'turn_id':'learner','speaker':'learner','transcript':'I am free tomorrow.'}]
    checks=validate_checks(check(r,quote='I am available tomorrow.'),[r],turns)
    assert checks[0]['validation']=='rejected'
    p=client.get('/v1/profile',headers=h).json();before=copy.deepcopy(p)
    apply_checks(p,checks,[r],'a','s',True,[],'scene','e');assert p==before
    no_use=check(r,result='not_used',quote='')
    checks=validate_checks(no_use,[r],turns);apply_checks(p,checks,[r],'a','s',True,[],'scene','e');assert p==before
    turns[0]['transcript']='I am available tomorrow.'
    forged=check(r,turn_id='partner');assert validate_checks(forged,[r],turns)[0]['validation']=='rejected'
    low=check(r);low['checks'][0]['confidence']='low';assert validate_checks(low,[r],turns)[0]['validation']=='rejected'


def test_evidence_updates_retention_and_due_without_task_mastery(client,application):
    h,user,s,lesson,r,_=setup_word(client,application);p=client.get('/v1/profile',headers=h).json()
    checks=validate_checks(check(r),[r],[{'turn_id':'learner','speaker':'learner','transcript':'I am available tomorrow.'}])
    now=time.time()
    apply_checks(p,checks,[r],'a1','s1',False,['example'],'scene1','e1',now=now)
    state=p['resource_states'][0];sense=state['senses'][r['sense_id']]
    assert state['retrieval']=='supported' and sense['retention']=='not_checked'
    apply_checks(p,checks,[r],'a2','s2',True,[],'scene2','e2',now=now+86400)
    assert state['retrieval']=='provisional'
    apply_checks(p,checks,[r],'a3','s3',True,[],'scene3','e3',now=now+9*86400)
    assert state['retrieval']=='demonstrated' and sense['retention']=='demonstrated'
    count=len(sense['observations']);apply_checks(p,checks,[r],'a3','s3',True,[],'scene3','e3',now=now+10*86400)
    assert len(sense['observations'])==count and p['target_states']==[]
    assert select_words(p,application.state.services.curriculum.target('ARRANGE.A2.s2'),[application.state.services.store.get('NotebookEntry',r['notebook_entry_id'],user)['payload']],now=now+10*86400)==[]
    sense['due_at']=now-1;state['due_at']=now-1
    row=application.state.services.store.get('LearnerProfile',user,user);application.state.services.store.put('LearnerProfile',user,user,p,expected=row['version'])
    recommendations=client.get('/v1/recommendations',headers=h).json()
    assert recommendations['due_count']==1 and recommendations['recommended']['lexical_only']
    assert select_words(p,application.state.services.curriculum.target('ARRANGE.A2.s2'),[application.state.services.store.get('NotebookEntry',r['notebook_entry_id'],user)['payload']])[0]['reason']=='到期复习'
    svc=application.state.services
    for i in range(4):svc.store.put('LearningPlan','cadence-'+str(i),user,{'planned_at':now+i,'lexical_driven':False})
    target,purpose,reason=svc.planner.select_target(p)
    assert target['target_id']=='ARRANGE.A2.s2' and '到期生词' in reason
    plan,_=svc.planner.plan(p,{})
    assert plan['resource_plan']['notebook_words'][0]['reason']=='到期复习'
    assert '保持主课程进度' not in svc.planner.select_target(p)[2]
    assert client.delete('/v1/notebook/'+r['notebook_entry_id'],headers=h).status_code==200
    assert client.get('/v1/recommendations',headers=h).json()['due_count']==0
    after=client.get('/v1/profile',headers=h).json()['resource_states'][0];assert len(after['senses'][r['sense_id']]['observations'])==count


def test_try_first_hint_retry_fixture_and_ownership(client,application):
    h,user,s,lesson,r,_=setup_word(client,application);other,_=register(client)
    id=s['view']['session_id'];pid=s['view']['lexical_practices'][0]['practice_id']
    path='/v1/sessions/'+id+'/vocabulary-attempts'
    body={'input_id':'meaning','practice_id':pid,'type':'request_hint'}
    assert client.post(path,headers=other,json=body).status_code==404
    first=client.post(path,headers=h,json=body);assert first.status_code==200,first.text
    assert r['meaning_zh'] in first.json()['hint'] and first.json()['example']==''
    assert client.post(path,headers=h,json=body).json()['session']['session_version']==first.json()['session']['session_version']
    assert client.post(path,headers=h,json={**body,'hint_level':'example'}).status_code==409
    example=client.post(path,headers=h,json={**body,'input_id':'example','hint_level':'example'}).json()
    assert example['example'] and set(example['support_used'])=={'meaning','pattern','example'}
    fixture=client.post(path,headers=h,json={'input_id':'fixture-text','practice_id':pid,'type':'text','text':'I am available tomorrow.'}).json()
    assert fixture['completed'] and fixture['lexical_results']==[]
    assert client.get('/v1/profile',headers=h).json()['resource_states'][0]['retrieval']=='not_checked'
    assert client.get('/v1/profile',headers=h).json()['target_states']==[]


def real_recording(svc,user):
    f=svc.settings.media_dir/'lexical-evidence.wav';f.write_bytes(asyncio.run(svc.provider.speech('test')))
    svc.store.put('AudioAsset','lexical-recording',user,{'purpose':'learner_recording','filename':f.name,'fixture':False,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
    async def transcribe(*args):return {'text':'I am available tomorrow.','quality':'final_transcript_available'}
    svc.provider.transcribe=transcribe
    return '/v1/media/lexical-recording'


def test_valid_probe_durable_update_and_dictionary_help(client,application):
    h,user,s,lesson,r,_=setup_word(client,application);svc=application.state.services
    id=s['view']['session_id'];row=svc.store.get('Session',id,user);v=copy.deepcopy(row['payload']);v['fixture']=False;svc.store.put('Session',id,user,v,expected=row['version'])
    audio=real_recording(svc,user)
    async def evaluate(resources,turns,context):return check(r,turn_id=turns[0]['turn_id'])
    svc.provider.evaluate_lexical=evaluate
    pid=s['view']['lexical_practices'][0]['practice_id'];path='/v1/sessions/'+id+'/vocabulary-attempts'
    # Looking up the target word in the learning probe is tracked server-side.
    assert client.post('/v1/vocabulary/lookup',headers=h,json={'word':'available','session_id':id}).status_code==200
    body={'input_id':'real-probe','practice_id':pid,'type':'speech','audio_ref':audio}
    response=client.post(path,headers=h,json=body);assert response.status_code==200,response.text
    assert response.json()['completed'] and '查词释义' in response.json()['support_used']
    state=client.get('/v1/profile',headers=h).json()['resource_states'][0];assert state['retrieval']=='supported'
    assert client.get('/v1/profile',headers=h).json()['target_states']==[]
    assert client.post(path,headers=h,json=body).status_code==200
    state2=client.get('/v1/profile',headers=h).json()['resource_states'][0];assert state2==state
    assert svc.store.get('LexicalPracticeAttempt',id+':real-probe',user)['payload']['evidence_valid']


def test_main_task_paraphrase_and_word_evidence_separate(client,application):
    h,user,s,lesson,r,_=setup_word(client,application);svc=application.state.services;audio=real_recording(svc,user)
    task=lesson['independent_task'];learner_id='learner'
    async def target_eval(task,turns,target):return {'result':'completed','confidence':'high','checks':[{'criterion':x,'result':'met','evidence_refs':[learner_id]} for x in task['assessment_contract']['critical_checks']],'diagnosis':[]}
    svc.provider.evaluate=target_eval
    async def lexical(resources,turns,context):return check(r,result='not_used',quote='')
    svc.provider.evaluate_lexical=lexical
    a={'attempt_id':'paraphrase','user_id':user,'session_id':'s-other','target_ids':lesson['target_ids'],'map_version':lesson['map_version'],'phase':'independent_application','fixture':False,'task_snapshot_ref':'snapshot','lexical_resources':[r],'support_used':[],
       'turns':[{'turn_id':learner_id,'speaker':'learner','transcript':'I am free at two.','audio_ref':audio,'asr':{'quality':'final_transcript_available'}}]}
    result=asyncio.run(svc.assessor.assess(a,task));assert result['validation']['status']=='accepted'
    p=client.get('/v1/profile',headers=h).json();assert p['target_states'][0]['independent']=='provisional' and p['resource_states'][0]['retrieval']=='not_checked'
    async def used(resources,turns,context):return check(r)
    svc.provider.evaluate_lexical=used
    a.update(attempt_id='word-used',session_id='s-new');a['turns'][0]['transcript']='I am available tomorrow.'
    result=asyncio.run(svc.assessor.assess(a,task));assert result['lexical_results'][0]['validation']=='accepted'
    p=client.get('/v1/profile',headers=h).json();assert p['resource_states'][0]['retrieval']=='provisional'
    assert asyncio.run(svc.assessor.assess(a,task))==result
    assert len(client.get('/v1/profile',headers=h).json()['resource_states'][0]['senses'][r['sense_id']]['observations'])==1
