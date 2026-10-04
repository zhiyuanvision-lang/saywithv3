import asyncio
import copy
import pytest
from test_backend import application, client, register, session
from backend.reply_feedback import ReplyAdvice


def test_advice_is_cached_tracks_help_and_does_not_update_mastery(application,client):
    headers,owner=register(client);state=session(client,application,headers)
    svc=application.state.services;sid=state['view']['session_id']
    row=svc.store.get('Session',sid,owner);s=copy.deepcopy(row['payload'])
    s['phase']='supported_practice'
    s['turns']=[{'turn_id':'reply-one','speaker':'learner','transcript':'I no free at ten.'}]
    svc.store.put('Session',sid,owner,s,expected=row['version'])
    calls=[]
    async def analyze(task,turns):
        calls.append(task)
        assert 'partner_private_facts' not in task
        return {'status':'correction','explanation_zh':'表示没空时用 I’m not free。',
                'expression':"I'm not free at ten.",'meaning_zh':'十点我没空。',
                'phrases':[{'expression':"I'm not free at …",'meaning_zh':'……我没空'}]}
    svc.provider.reply_advice=analyze
    path=f'/v1/sessions/{sid}/turns/reply-one/feedback'
    first=client.post(path,headers=headers);assert first.status_code==200,first.text
    assert first.json()['audio_ref'];assert client.post(path,headers=headers).json()==first.json()
    assert len(calls)==1
    updated=svc.sessions.view(sid,owner)
    assert updated['view']['support_used']==['回答示范']
    assert not svc.store.get('LearnerProfile',owner,owner)['payload']['target_states']
    other,_=register(client);assert client.post(path,headers=other).status_code==404
    row=svc.store.get('Session',sid,owner);s=row['payload'];s['phase']='independent_application'
    svc.store.put('Session',sid,owner,s,expected=row['version'])
    assert client.post(path,headers=headers).status_code==409
    row=svc.store.get('Session',sid,owner);s=row['payload'];s['phase']='finished'
    svc.store.put('Session',sid,owner,s,expected=row['version'])
    assert client.post(path,headers=headers).status_code==200


def test_feedback_requires_usable_example_and_never_corrects_uncertain_speech():
    with pytest.raises(ValueError):
        ReplyAdvice(status='correction',explanation_zh='错误')
    value=ReplyAdvice(status='uncertain',explanation_zh='请回听录音',expression='invented',meaning_zh='编造',phrases=[])
    assert not value.expression

@pytest.mark.parametrize('failure',[False,True])
def test_each_reply_analyzed_without_blocking_on_feedback_failure(application,client,failure):
    from backend.providers import ProviderFailure
    headers,owner=register(client);state=session(client,application,headers)
    svc=application.state.services;sid=state['view']['session_id']
    row=svc.store.get('Session',sid,owner);s=row['payload'];s['phase']='supported_practice'
    svc.store.put('Session',sid,owner,s,expected=row['version'])
    calls=[]
    async def analyze(task,turns):
        calls.append(turns[-1]['transcript'])
        if failure:raise ProviderFailure('temporarily unavailable')
        return {'status':'clear','explanation_zh':'表达清楚。','expression':'','meaning_zh':'','phrases':[]}
    svc.provider.reply_advice=analyze
    entry={'session_id':sid,'task_id':s['task']['task_id'],'input_id':'advice-test','type':'text',
           'text':'How about four?','recorded_at':'2026-10-04T02:00:00Z'}
    response=client.post(f'/v1/sessions/{sid}/inputs',json=entry,headers=headers)
    assert response.status_code==200,response.text
    assert calls==['How about four?']
    assert client.post(f'/v1/sessions/{sid}/inputs',json=entry,headers=headers).status_code==200
    assert len(calls)==1
    assert svc.sessions.view(sid,owner)['view']['support_used']==[]

def test_preanalyzed_text_advice_gets_audio_without_duplicate_insert(application,client):
    from backend.reply_feedback import analyze_reply
    headers,owner=register(client);state=session(client,application,headers)
    svc=application.state.services;sid=state['view']['session_id']
    row=svc.store.get('Session',sid,owner);s=copy.deepcopy(row['payload'])
    turn={'turn_id':'preanalyzed','speaker':'learner','transcript':'I no free at ten.'}
    s.update(phase='supported_practice',turns=[turn])
    svc.store.put('Session',sid,owner,s,expected=row['version'])
    calls=[]
    async def analyze(task,turns):
        calls.append(1)
        return {'status':'correction','explanation_zh':'用 I’m not free 表示没空。',
                'expression':"I'm not free at ten.",'meaning_zh':'十点我没空。','phrases':[]}
    svc.provider.reply_advice=analyze
    asyncio.run(analyze_reply(svc.sessions,sid,owner,s,turn))
    before=svc.store.get('ReplyFeedback',sid+'/preanalyzed',owner)
    assert before['payload']['audio_ref'] is None
    path=f'/v1/sessions/{sid}/turns/preanalyzed/feedback'
    response=client.post(path,headers=headers)
    assert response.status_code==200,response.text
    assert response.json()['audio_ref']
    after=svc.store.get('ReplyFeedback',sid+'/preanalyzed',owner)
    assert after['version']==before['version']+1
    assert len(calls)==1
    assert client.post(path,headers=headers).json()==response.json()
    assert svc.store.get('ReplyFeedback',sid+'/preanalyzed',owner)['version']==after['version']

def test_concurrent_audio_requests_reuse_one_cache_and_support_record(application,client):
    from backend.reply_feedback import reply_feedback
    headers,owner=register(client);state=session(client,application,headers)
    svc=application.state.services;sid=state['view']['session_id']
    row=svc.store.get('Session',sid,owner);s=copy.deepcopy(row['payload'])
    s.update(phase='supported_practice',turns=[{'turn_id':'concurrent','speaker':'learner','transcript':'I no free.'}])
    svc.store.put('Session',sid,owner,s,expected=row['version'])
    advice={'status':'correction','explanation_zh':'需要 be 动词。','expression':"I'm not free.",
            'meaning_zh':'我没空。','phrases':[],'turn_id':'concurrent','audio_ref':None}
    svc.store.put('ReplyFeedback',sid+'/concurrent',owner,advice)
    async def run():
        calls=[];both=asyncio.Event()
        async def audio(*args):
            calls.append(1)
            if len(calls)==2:both.set()
            await both.wait()
            return {'audio_ref':'/v1/media/audio-'+str(len(calls))}
        svc.generator.audio=audio
        results=await asyncio.gather(reply_feedback(svc.sessions,sid,owner,'concurrent'),reply_feedback(svc.sessions,sid,owner,'concurrent'))
        assert results[0]==results[1]
    asyncio.run(run())
    assert svc.store.get('ReplyFeedback',sid+'/concurrent',owner)['version']==2
    assert svc.sessions.view(sid,owner)['view']['support_used']==['回答示范']


def test_late_analysis_does_not_overwrite_ready_audio(application,client):
    from backend.reply_feedback import cache_new_advice
    headers,owner=register(client);svc=application.state.services
    cached={'status':'clear','explanation_zh':'表达清楚。','expression':'','meaning_zh':'','phrases':[],
            'turn_id':'late','audio_ref':'/v1/media/already-ready'}
    svc.store.put('ReplyFeedback','late',owner,cached)
    assert cache_new_advice(svc.store,'late',owner,{**cached,'audio_ref':None})==cached
    assert svc.store.get('ReplyFeedback','late',owner)['version']==1
