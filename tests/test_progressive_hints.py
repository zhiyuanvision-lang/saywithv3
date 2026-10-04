import asyncio,json,httpx
from test_backend import application,client,register,session
from test_v6_teaching import shadow,next_round
from backend.providers import APIProvider
from backend.config import Settings


def test_hint_repair_keeps_only_public_context_and_one_frame():
    calls=[]
    def respond(request):
        body=json.loads(request.content);calls.append(json.loads(body['messages'][1]['content']))
        expression='How about ___?\nAre you free ___?' if len(calls)==1 else 'How about ___?'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'expression':expression,'meaning_zh':'……怎么样？'})}}]})
    async def run():
        provider=APIProvider(Settings(),httpx.MockTransport(respond))
        try:
            result=await provider.hint({'learner_facts':{'available_times':['15:00']},'learner_prompt':'提出替代时间','partner_facts':{'secret':'PRIVATE'}},[{'speaker':'partner','text':'Ten does not work.'}],[],{},'pattern')
            assert result['hint_content']['expression']=='How about ___?'
        finally:await provider.close()
    asyncio.run(run())
    assert len(calls)==2 and calls[1]['repair_feedback']
    assert 'PRIVATE' not in json.dumps(calls)
    assert calls[0]['turns'][-1]['text']=='Ten does not work.'


def test_progressive_hint_example_audio_and_next_turn_context(client,application):
    headers,owner=register(client);state=next_round(client,headers,shadow(client,headers,session(client,application,headers)))
    sid=state['view']['session_id'];before=state['turns']
    def hint(level,key):
        response=client.post(f'/v1/sessions/{sid}/inputs',headers=headers,json={'session_id':sid,'task_id':state['view']['task_id'],'input_id':key,'type':'request_hint','hint_level':level,'recorded_at':'2026-10-04T03:00:00Z'})
        assert response.status_code==200;return response.json()
    frame=hint('pattern','frame');example=hint('example','example')
    assert frame['audio_ref'] is None and '___' in frame['hint_content']['expression']
    assert example['audio_ref'] and '___' not in example['hint_content']['expression']
    assert client.get(example['audio_ref'],headers=headers).status_code==200
    assert client.get(f'/v1/sessions/{sid}',headers=headers).json()['turns']==before
    row=application.state.services.store.get('Session',sid,owner);s=row['payload'];s['turns'].append({'turn_id':'closing','speaker':'partner','text':'See you then!'})
    application.state.services.store.put('Session',sid,owner,s,expected=row['version'])
    assert hint('pattern','closing-hint')['hint_content']['expression']=='See you ___!'
    assert '完整示例' in application.state.services.store.get('Session',sid,owner)['payload']['support_used']


def test_example_repairs_unfilled_frame():
    replies=['How about ___?','How about three in the afternoon?'];calls=[]
    def respond(request):
        calls.append(json.loads(request.content));value={'expression':replies[len(calls)-1]}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]})
    async def run():
        provider=APIProvider(Settings(),httpx.MockTransport(respond))
        try:assert (await provider.hint({'learner_facts':{'available_times':['15:00']}},[],[],{},'example'))['text']==replies[-1]
        finally:await provider.close()
    asyncio.run(run());assert len(calls)==2
