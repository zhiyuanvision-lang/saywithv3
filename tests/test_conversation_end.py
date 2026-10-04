import asyncio
import copy
import pytest
from test_backend import application,client,register,session
from backend.conversation_end import learner_closed

@pytest.mark.parametrize('text',['See you.','See you then!','Okay, thanks, see you later.','Goodbye!','Bye bye.','再见。'])
def test_whole_farewell(text):
    assert learner_closed({'transcript':text},{})

@pytest.mark.parametrize('text',['How do I say see you?','I cannot see you tomorrow.','See you at three?','The phrase see you means goodbye.','"See you"',''])
def test_not_a_farewell(text):
    assert not learner_closed({'transcript':text},{'conversation_closed':False})
    assert not learner_closed({'transcript':'How do I say see you?'},{'conversation_closed':True})

def test_unreliable_audio_never_ends_task():
    assert not learner_closed({'transcript':'See you.','audio_ref':'recording','asr':{'quality':'uncertain'}},{'conversation_closed':True})

@pytest.mark.parametrize('index,expected',[(0,'supported_practice'),(2,'guided_feedback')])
def test_guided_farewell_advances_and_retry_is_idempotent(application,client,index,expected):
    headers,owner=register(client);state=session(client,application,headers)
    svc=application.state.services;sid=state['view']['session_id']
    row=svc.store.get('Session',sid,owner);s=copy.deepcopy(row['payload'])
    asyncio.run(svc.sessions.support.prepare(s,owner))
    s.update(phase='supported_practice',guided_index=index,task=copy.deepcopy(s['guided_tasks'][index]))
    svc.store.put('Session',sid,owner,s,expected=row['version'])
    entry={'session_id':sid,'task_id':s['task']['task_id'],'input_id':'bye-input','type':'text','text':'See you.',
           'recorded_at':'2026-10-04T04:00:00Z'}
    path=f'/v1/sessions/{sid}/inputs'
    result=client.post(path,headers=headers,json=entry);assert result.status_code==200,result.text
    assert result.json()['continuation']=='advanced'
    updated=svc.sessions.view(sid,owner);assert updated['view']['phase']==expected
    if index==0:assert updated['view']['guided_round']==2
    assert client.post(path,headers=headers,json=entry).json()==result.json()
    assert svc.sessions.view(sid,owner)==updated
    assert len(svc.store.list('TaskAttempt',owner))==1
    assert not svc.store.get('LearnerProfile',owner,owner)['payload']['target_states']

def test_premature_goodbye_finishes_without_claiming_mastery(application,client):
    headers,owner=register(client);state=session(client,application,headers)
    svc=application.state.services;sid=state['view']['session_id']
    row=svc.store.get('Session',sid,owner);s=row['payload'];s['phase']='independent_application'
    s['task']['allowed_support']=['text_input'];s['task']['interaction_policy']={'allow_text_input':True}
    svc.store.put('Session',sid,owner,s,expected=row['version'])
    entry={'session_id':sid,'task_id':s['task']['task_id'],'input_id':'bye-input','type':'text','text':'Goodbye!',
           'recorded_at':'2026-10-04T04:00:00Z'}
    # Service-level input keeps this test focused on closing rather than a task's text policy.
    original=svc.sessions.support.actions
    svc.sessions.support.actions=lambda session:original(session)+['text_input']
    result=client.post(f'/v1/sessions/{sid}/inputs',headers=headers,json=entry)
    assert result.status_code==200,result.text
    assert result.json()['continuation']=='advanced'
    updated=svc.sessions.view(sid,owner);assert updated['view']['phase']=='finished'
    assert updated['view']['assessment']['target_results'][0]['result']=='unjudgeable'
    assert not svc.store.get('LearnerProfile',owner,owner)['payload']['target_states']

def test_auto_transition_failure_can_be_resumed(application,client):
    from backend.providers import ProviderFailure
    headers,owner=register(client);state=session(client,application,headers)
    svc=application.state.services;sid=state['view']['session_id']
    row=svc.store.get('Session',sid,owner);s=copy.deepcopy(row['payload'])
    asyncio.run(svc.sessions.support.prepare(s,owner));s.update(phase='supported_practice',guided_index=0,task=copy.deepcopy(s['guided_tasks'][0]))
    svc.store.put('Session',sid,owner,s,expected=row['version'])
    original=svc.assessor.assess
    async def unavailable(*args,**kwargs):raise ProviderFailure('temporary evaluation failure')
    svc.assessor.assess=unavailable
    entry={'session_id':sid,'task_id':s['task']['task_id'],'input_id':'bye-retry','type':'text','text':'See you.',
           'recorded_at':'2026-10-04T04:00:00Z'}
    result=client.post(f'/v1/sessions/{sid}/inputs',headers=headers,json=entry)
    assert result.status_code==200,result.text
    assert result.json()['continuation']=='retry'
    pending=svc.sessions.view(sid,owner);assert pending['view']['phase']=='evaluating'
    svc.assessor.assess=original
    resumed=client.post(f'/v1/sessions/{sid}/next',headers=headers,json={'expected_session_version':pending['session_version'],'advance_round':True})
    assert resumed.status_code==200,resumed.text
    assert resumed.json()['view']['guided_round']==2
    assert len(svc.store.list('TaskAttempt',owner))==1
