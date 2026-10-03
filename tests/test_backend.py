import asyncio
import copy
import io
import json
import time
import wave
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from backend.app import create_app
from backend.config import Settings
from backend.contracts import CONTRACTS
from backend.providers import FixtureProvider
from backend.store import Conflict, Missing, uid

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def application(tmp_path):
    url='sqlite:///'+str(tmp_path/'db.sqlite')
    admin_engine=None
    if os.getenv('SAYWITH_TEST_DATABASE_URL'):
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        base=make_url(os.environ['SAYWITH_TEST_DATABASE_URL']);name='test_'+uid().replace('-','')
        admin_engine=create_engine(base,isolation_level='AUTOCOMMIT')
        with admin_engine.connect() as c:c.execute(text('CREATE DATABASE '+name))
        url=base.set(database=name).render_as_string(hide_password=False)
    settings=Settings(workspace=ROOT,mode='fixture',database_url=url,
        media_dir=tmp_path/'media',admin_token='test-admin')
    app=create_app(settings)
    yield app
    app.state.services.store.engine.dispose()
    if admin_engine:
        with admin_engine.connect() as c:c.execute(text('DROP DATABASE '+name+' WITH (FORCE)'))
        admin_engine.dispose()

@pytest.fixture
def client(application):
    with TestClient(application) as c:yield c

def register(client):
    response=client.post('/v1/users',json={'reference_stage':'A2'})
    assert response.status_code==201,response.text
    return {'Authorization':'Bearer '+response.json()['access_token']},response.json()['user_id']

def generate(client,app,headers,key='one'):
    r=client.post('/v1/course-generation-jobs',json={'target_id':'ARRANGE.A2.s2'},headers={**headers,'Idempotency-Key':key})
    assert r.status_code==202,r.text
    asyncio.run(app.state.services.generator.run_one('test-worker'))
    r=client.get('/v1/course-generation-jobs/'+r.json()['job_id'],headers=headers)
    assert r.json()['state']=='preview_ready',r.text
    return r.json()

def session(client,app,headers):
    job=generate(client,app,headers)
    r=client.post('/v1/sessions',json={'lesson_id':job['result_lesson_id']},headers=headers)
    assert r.status_code==201,r.text
    return r.json()

def next_phase(client,headers,s):
    r=client.post('/v1/sessions/'+s['view']['session_id']+'/next',headers=headers,
                  json={'expected_session_version':s['session_version']})
    assert r.status_code==200,r.text
    return r.json()

def send(client,headers,s,kind='text',text='How about two?',input_id='input1'):
    body={'session_id':s['view']['session_id'],'task_id':s['view']['task_id'],'input_id':input_id,'type':kind,
        'recorded_at':'2026-10-03T12:00:00+00:00','expected_session_version':s['session_version']}
    if kind=='text':body['text']=text
    return client.post('/v1/sessions/'+s['view']['session_id']+'/inputs',headers=headers,json=body)

def test_all_architecture_examples_remain_parseable():
    data=json.loads((ROOT/'research/system-dataflow-2026-10-02/contracts.examples.json').read_text())
    for name,example in data.items():CONTRACTS[name].model_validate(example)

def test_auth_and_private_data(client,application):
    a,_=register(client);b,_=register(client)
    assert client.get('/v1/profile').status_code==401
    job=generate(client,application,a)
    assert client.get('/v1/course-generation-jobs/'+job['job_id'],headers=b).status_code==404
    assert client.get('/internal/v1/lessons/'+job['result_lesson_id'],headers=a).status_code==403
    assert client.post('/v1/sessions',headers=b,json={'lesson_id':job['result_lesson_id']}).status_code==404
    assert 'partner_private_facts' not in json.dumps(job)

def test_idempotency_and_cancel(client,application):
    h,user=register(client);headers={**h,'Idempotency-Key':'key'}
    a=client.post('/v1/course-generation-jobs',headers=headers,json={'target_id':'ARRANGE.A2.s2'}).json()
    b=client.post('/v1/course-generation-jobs',headers=headers,json={'target_id':'ARRANGE.A2.s2'}).json()
    assert a['job_id']==b['job_id']
    assert client.post('/v1/course-generation-jobs',headers=headers,json={'target_id':'ARRANGE.A2.s1'}).status_code==409
    claimed=application.state.services.store.claim('worker')
    assert claimed['id']==a['job_id']
    client.post('/v1/course-generation-jobs/'+a['job_id']+'/cancel',headers=h)
    with pytest.raises(Conflict):application.state.services.store.advance(claimed,'approved',claimed['payload'])
    assert not application.state.services.store.list('LessonPackage',user)

def test_worker_lease_is_exclusive_and_recovers(application,client):
    h,_=register(client)
    r=client.post('/v1/course-generation-jobs',headers={**h,'Idempotency-Key':'key'},json={'target_id':'ARRANGE.A2.s2'})
    store=application.state.services.store
    first=store.claim('first',seconds=10)
    assert store.claim('second') is None
    with store.transaction() as c:c.execute(update(store.jobs).where(store.jobs.c.id==first['id']).values(lease_until=time.time()-1))
    second=store.claim('second')
    assert second['id']==first['id'] and second['version']>first['version']
    with pytest.raises(Conflict):store.advance(first,'approved',{})

def test_entire_teaching_flow_and_fixture_not_mastery(application,client):
    h,user=register(client);s=session(client,application,h);id=s['view']['session_id']
    assert s['view']['phase']=='learning'
    # Learner recordings carry no synthesized-text field; opening lookup must skip them.
    application.state.services.store.put('AudioAsset','unrelated-recording',user,{'purpose':'learner_recording','filename':'recording.wav'})
    assert client.post('/v1/sessions/'+id+'/next',headers=h,json={'expected_session_version':s['session_version']}).status_code==409
    s=client.post('/v1/sessions/'+id+'/learn',headers=h,json={'material_index':0,'personal_text':'How about Friday?'}).json()
    s=next_phase(client,h,s)
    assert not s['view']['materials']
    assert 'partner_private_facts' not in json.dumps(s)
    assert 'assessment_contract' not in json.dumps(s)
    r=send(client,h,s);assert r.status_code==200,r.text
    repeat=send(client,h,s);assert repeat.json()['turn_id']==r.json()['turn_id']
    assert send(client,h,s,text='different').status_code==409
    s=client.get('/v1/sessions/'+id,headers=h).json();s=next_phase(client,h,s)
    assert s['view']['phase']=='independent_application'
    assert send(client,h,s,kind='request_hint',input_id='hint').status_code==409
    r=send(client,h,s,input_id='independent');assert r.status_code==200,r.text
    r=client.post('/v1/sessions/'+id+'/finish',headers=h)
    assert r.status_code==200,r.text
    assert r.json()['validation']['status']=='rejected'
    assert client.post('/v1/sessions/'+id+'/finish',headers=h).json()==r.json()
    assert client.get('/v1/profile',headers=h).json()['target_states']==[]

def test_unknown_fixture_target_requires_review(application,client):
    h,_=register(client)
    r=client.post('/v1/course-generation-jobs',headers={**h,'Idempotency-Key':'k'},json={'target_id':'ARRANGE.A2.s1'})
    asyncio.run(application.state.services.generator.run_one('worker'))
    assert client.get('/v1/course-generation-jobs/'+r.json()['job_id'],headers=h).json()['state']=='needs_review'

def test_invalid_course_does_not_publish(application,client):
    h,_=register(client);svc=application.state.services
    original=svc.provider.generate
    async def broken(a,t,feedback=None):
        d=await original(a,t);d['independent_task']['partner_private_facts']['available_times']=['23:00'];return d
    svc.provider.generate=broken
    r=client.post('/v1/course-generation-jobs',headers={**h,'Idempotency-Key':'broken'},json={'target_id':'ARRANGE.A2.s2'})
    asyncio.run(svc.generator.run_one('worker'))
    assert client.get('/v1/course-generation-jobs/'+r.json()['job_id'],headers=h).json()['state']=='needs_review'
    assert not svc.store.list('LessonPackage')

def test_audio_access_is_owner_scoped(application,client):
    a,_=register(client);b,_=register(client)
    s=session(client,application,a);ref=s['view']['materials'][0]['audio_ref']
    assert client.get(ref,headers=a).status_code==200
    assert client.get(ref,headers=b).status_code==404
    other=session(client,application,b);otherref=other['view']['materials'][0]['audio_ref']
    assert otherref!=ref and client.get(otherref,headers=b).status_code==200

def test_recording_validation(client):
    h,_=register(client)
    assert client.post('/v1/media',headers=h,files={'audio':('bad.wav',b'bad','audio/wav')}).status_code==422
    b=io.BytesIO()
    with wave.open(b,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\x01\0'*1600)
    r=client.post('/v1/media',headers=h,files={'audio':('audio.wav',b.getvalue(),'audio/wav')})
    assert r.status_code==201,r.text

def test_map_release_review_activation_and_immutability(application,client,tmp_path):
    h,_=register(client)
    svc=application.state.services
    file=tmp_path/'source.json';file.write_text('{"text":"source"}')
    # Normalization rejects source paths outside the controlled workspace.
    with pytest.raises(ValueError):svc.curriculum.normalize({'schema_version':'1.0','catalog_version':'external','status':'draft',
        'sources':[{'source_id':'s1','document_ref':str(file)}]})
    catalog=svc.store.list('SourceCatalog')[0]['payload']
    t=svc.curriculum.target('ARRANGE.A2.s2');t.update(map_version='test-v2',target_version='test-v2')
    t['contract']['target_version']='test-v2'
    review=svc.curriculum.review(catalog['catalog_version'],[t],'test reviewer')
    release=svc.curriculum.publish(review['review_id'])
    assert release['map_version']=='test-v2'
    assert svc.curriculum.target('ARRANGE.A2.s2')['map_version']=='test-v2'
    assert client.get('/v1/curriculum/targets',headers=h).json()['map_version']=='test-v2'
    assert client.get('/health').json()['map_version']=='test-v2'
    assert svc.curriculum.target('ARRANGE.A2.s2','1.0.1-model-reviewed')['map_version']=='1.0.1-model-reviewed'
    with pytest.raises(Conflict):svc.curriculum.publish(review['review_id'])

def test_evidence_dedup_and_retention_dimensions(application,client):
    h,user=register(client);svc=application.state.services
    # Use a synthetic provider only inside this test; no production learner claims.
    s=session(client,application,h)
    lesson=svc.store.get('LessonPackage',s['view']['lesson_id'],user)['payload'];task=lesson['independent_task']
    async def evaluated(task,turns,target):
        return {'result':'completed','confidence':'high','checks':[{'criterion':task['assessment_contract']['critical_checks'][0],
            'result':'met','evidence_refs':['turn-learner']}],'diagnosis':[]}
    svc.provider.evaluate=evaluated
    recording=application.state.services.settings.media_dir/'evidence.wav'
    recording.write_bytes(asyncio.run(svc.provider.speech('test evidence')))
    import hashlib
    svc.store.put('AudioAsset','test-evidence',user,{'purpose':'learner_recording','filename':recording.name,
        'fixture':False,'sha256':hashlib.sha256(recording.read_bytes()).hexdigest()})
    def attempt(id,session,fixture=False,textonly=False):
        return {'attempt_id':id,'user_id':user,'session_id':session,'target_ids':lesson['target_ids'],'map_version':lesson['map_version'],
            'phase':'independent_application','fixture':fixture,'task_snapshot_ref':'snapshot',
            'turns':[{'turn_id':'turn-learner','speaker':'learner','transcript':'How about two?',
                **({} if textonly else {'audio_ref':'/v1/media/test-evidence','asr':{'quality':'final_transcript_available'}})}], 'support_used':[]}
    a=attempt('a1','session1')
    first=asyncio.run(svc.assessor.assess(a,task))
    assert first['validation']['status']=='accepted'
    assert asyncio.run(svc.assessor.assess(a,task))==first
    p=svc.store.get('LearnerProfile',user,user)['payload'];state=p['target_states'][0]
    assert state['independent']=='provisional' and state['retention']=='not_checked'
    assert len(state['evidence_ids'])==1
    row=svc.store.get('LearnerProfile',user,user);p=row['payload']
    p['target_states'][0]['observations'][0]['time']-=8*86400
    svc.store.put('LearnerProfile',user,user,p,expected=row['version'])
    task=copy.deepcopy(task);task['scenario_signature']='arrange-work'
    asyncio.run(svc.assessor.assess(attempt('a2','session2'),task))
    state=svc.store.get('LearnerProfile',user,user)['payload']['target_states'][0]
    assert state['independent']=='demonstrated' and state['retention']=='demonstrated' and state['transfer']=='demonstrated'
    result=asyncio.run(svc.assessor.assess(attempt('a3','s3',textonly=True),task))
    assert result['validation']['status']=='rejected'

def test_assessment_rejects_invented_evidence(application,client):
    h,user=register(client);svc=application.state.services;s=session(client,application,h)
    task=svc.store.get('LessonPackage',s['view']['lesson_id'],user)['payload']['independent_task']
    async def bad(*args):return {'result':'completed','confidence':'high','checks':[{'criterion':task['assessment_contract']['critical_checks'][0],
        'result':'met','evidence_refs':['made-up']}],'diagnosis':[]}
    svc.provider.evaluate=bad
    recording=svc.settings.media_dir/'valid-evidence.wav'
    recording.write_bytes(asyncio.run(svc.provider.speech('test')))
    import hashlib
    svc.store.put('AudioAsset','valid-evidence',user,{'purpose':'learner_recording','filename':recording.name,
        'fixture':False,'sha256':hashlib.sha256(recording.read_bytes()).hexdigest()})
    a={'attempt_id':'bad','user_id':user,'session_id':'x','map_version':svc.curriculum.repository.version,'target_ids':['ARRANGE.A2.s2'],
       'phase':'independent_application','task_snapshot_ref':'x','support_used':[],
       'turns':[{'turn_id':'real','speaker':'learner','transcript':'How about two?','audio_ref':'/v1/media/valid-evidence','asr':{'quality':'final_transcript_available'}}]}
    invalid=asyncio.run(svc.assessor.assess(a,task))
    assert invalid['validation']['status']=='rejected'
    assert '证据引用不存在' in invalid['validation']['checks']
    async def malformed(*args):return {'result':'completed','confidence':'high','checks':'wrong-type'}
    svc.provider.evaluate=malformed;a['attempt_id']='malformed'
    malformed_result=asyncio.run(svc.assessor.assess(a,task))
    assert malformed_result['validation']['status']=='rejected'
    assert '模型评价结构不合法' in malformed_result['validation']['checks']
    assert not svc.store.get('LearnerProfile',user,user)['payload']['target_states']


def test_unsafe_partner_reply_never_enters_session(application,client):
    h,_=register(client);s=session(client,application,h);id=s['view']['session_id']
    s=client.post('/v1/sessions/'+id+'/learn',headers=h,json={'material_index':0,'personal_text':'How about Friday?'}).json()
    s=next_phase(client,h,s)
    calls=[]
    async def reject(task,turns,reply,phase):
        calls.append(reply);return {'decision':'fail','reasons':['unsafe test reply']}
    application.state.services.provider.review_dialogue=reject
    assert send(client,h,s).status_code==422
    after=client.get('/v1/sessions/'+id,headers=h).json()
    assert after['turns']==s['turns'] and after['session_version']==s['session_version']
    assert len(calls)==2


def test_scheduler_advances_only_after_complete_band_and_prioritizes_support(application,client):
    _,user=register(client);svc=application.state.services
    profile=svc.store.get('LearnerProfile',user,user)['payload']
    profile['target_states']=[{'target_id':'ARRANGE.A2.s2','independent':'supported'}]
    assignment,target=svc.planner.plan(profile,{})
    assert target['target_id']=='ARRANGE.A2.s2' and assignment['purpose']=='consolidation'
    targets=svc.curriculum.list_targets(stage='A2')
    profile['target_states']=[{'target_id':t['target_id'],'independent':'demonstrated','transfer':'demonstrated'} for t in targets]
    _,target=svc.planner.plan(profile,{})
    assert target['reference_stage']=='B1'
    profile['target_states'][0]['due_at']=0
    assignment,target=svc.planner.plan(profile,{})
    assert target['reference_stage']=='A2' and assignment['purpose']=='retention'
