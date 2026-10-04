import asyncio
import copy
import hashlib
import json
import httpx
import pytest
from test_backend import application, client, register, session
from backend.config import Settings
from backend.providers import APIProvider, ProviderFailure


def test_evaluation_repairs_schema_without_accepting_nested_result():
    requests=[]
    def transport(request):
        data=json.loads(request.content);requests.append(data)
        candidate={'assessment':{'result':'completed'}} if len(requests)==1 else {'result':'partial','confidence':'high','checks':[],'diagnosis':[]}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(candidate)}}]})
    async def run():
        provider=APIProvider(Settings(),httpx.MockTransport(transport))
        try:assert (await provider.evaluate({'assessment_contract':{'critical_checks':[]}},[],{}))['result']=='partial'
        finally:await provider.close()
    asyncio.run(run());assert len(requests)==2
    payload=json.loads(requests[1]['messages'][1]['content']);assert payload['output_schema'];assert payload['repair_feedback']['invalid_output']


def test_repeated_invalid_evaluation_is_service_failure():
    async def run():
        provider=APIProvider(Settings(),httpx.MockTransport(lambda r:httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"checks":"bad"}'}}]})))
        try:
            with pytest.raises(ProviderFailure,match='schema'):await provider.evaluate({},[],{})
        finally:await provider.close()
    asyncio.run(run())


@pytest.mark.parametrize('valid_completion',[True,False])
def test_transcript_visible_before_reply_and_only_valid_completion_ends(application,client,valid_completion):
    headers,owner=register(client);state=session(client,application,headers);svc=application.state.services;sid=state['view']['session_id']
    row=svc.store.get('Session',sid,owner);s=copy.deepcopy(row['payload']);s['phase']='independent_application';s['fixture']=False
    s['task']['assessment_contract']['critical_checks']=['说明原时间不方便'];s['task']['modality']='spoken_interaction'
    svc.store.put('Session',sid,owner,s,expected=row['version'])
    recording=svc.settings.media_dir/'completion.wav';recording.write_bytes(asyncio.run(svc.provider.speech('test-only controlled evidence')))
    svc.store.put('AudioAsset','completion-recording',owner,{'purpose':'learner_recording','filename':recording.name,'fixture':False,'sha256':hashlib.sha256(recording.read_bytes()).hexdigest()})
    transcribes=[];evaluations=[]
    async def run():
        parsed=asyncio.Event();release=asyncio.Event()
        async def transcribe(*args):transcribes.append(1);return {'text':"That doesn't work for me.",'quality':'final_transcript_available'}
        async def dialogue(*args,**kwargs):parsed.set();await release.wait();return {'text':'Okay, see you then.','conversation_complete':True}
        async def evaluate(task,turns,target):
            evaluations.append(1);ref=next(t['turn_id'] for t in turns if t['speaker']=='learner')
            return {'result':'completed','confidence':'high','checks':[{'criterion':'说明原时间不方便','result':'met','evidence_refs':[ref if valid_completion else 'invented']}],'diagnosis':[]}
        svc.provider.transcribe=transcribe;svc.provider.dialogue=dialogue;svc.provider.evaluate=evaluate
        entry={'schema_version':'1.0','session_id':sid,'task_id':s['task']['task_id'],'input_id':'real-input','type':'speech','audio_ref':'/v1/media/completion-recording','recorded_at':'2026-10-04T02:00:00Z'}
        submission=asyncio.create_task(svc.sessions.input(sid,owner,entry));await parsed.wait()
        progress=svc.sessions.input_progress(sid,owner,'real-input');assert progress['status']=='responding';assert progress['transcript']=="That doesn't work for me."
        assert 'asr' not in progress and 'request_hash' not in progress
        assert not svc.store.get('Session',sid,owner)['payload']['turns']
        release.set();result=await submission;assert await svc.sessions.input(sid,owner,entry)==result
        assert len(transcribes)==1 and len(evaluations)==1
    asyncio.run(run())
    saved=svc.sessions.view(sid,owner);assert saved['view']['phase']==('finished' if valid_completion else 'independent_application')
    profile=svc.store.get('LearnerProfile',owner,owner)['payload'];assert bool(profile['target_states'])==valid_completion
    other,_=register(client);assert client.get(f'/v1/sessions/{sid}/inputs/real-input',headers=other).status_code==404
    assert client.get(f'/v1/sessions/{sid}/inputs/real-input',headers=headers).json()['status']=='completed'
