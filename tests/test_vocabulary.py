import copy
from test_backend import application,client,register

def test_lookup_notebook_canonical_identity_ownership_and_signals(client,application):
    h,_=register(client);other,_=register(client)
    before=client.get('/v1/profile',headers=h).json()
    r=client.post('/v1/vocabulary/lookup',headers=h,json={'word':'being','context':'I am being careful.'})
    assert r.status_code==200,r.text
    assert r.json()['word']=='be' and r.json()['tapped_word']=='being'
    p=client.get('/v1/profile',headers=h).json()
    assert p['target_states']==before['target_states']
    signal=next(x for x in p['resource_states'] if x['resource_id']=='lexeme:be')
    assert signal['understanding']=='not_checked' and signal['lookup_count']==1
    body={'word':'available','context':'Are you available tomorrow?'}
    saved=client.post('/v1/notebook',headers=h,json=body)
    assert saved.status_code==201,saved.text
    id=saved.json()['id']
    assert client.post('/v1/notebook',headers=h,json=body).json()['id']==id
    assert len(client.get('/v1/notebook',headers=h).json()['items'])==1
    assert client.get('/v1/notebook/'+id,headers=other).status_code==404
    assert client.delete('/v1/notebook/'+id,headers=other).status_code==404
    p=client.get('/v1/profile',headers=h).json()
    assert p['target_states']==before['target_states']
    s=next(x for x in p['resource_states'] if x['resource_id']=='lexeme:available')
    assert s['practice_signal']=='self_selected' and s['understanding']=='not_checked'
    plan,_=application.state.services.planner.plan(p,{})
    assert plan['resource_plan']['notebook_words'][0]['word']=='available'
    assert client.delete('/v1/notebook/'+id,headers=h).json()['removed']
    assert client.get('/v1/notebook',headers=h).json()['items']==[]
    p=client.get('/v1/profile',headers=h).json()
    state=next(x for x in p['resource_states'] if x['resource_id']=='lexeme:available')
    assert state['notebook_active']==False and len(state['observations'])>=1
    assert p['target_states']==before['target_states']

def test_vocabulary_validation_and_detail(client):
    h,_=register(client)
    assert client.post('/v1/vocabulary/lookup',headers=h,json={'word':'../secret'}).status_code==422
    assert client.post('/v1/notebook',headers=h,json={'word':'somewordzzzzz'}).status_code==404
    assert client.get('/v1/notebook').status_code==401
    r=client.get('/v1/vocabulary/knowledge?word=available',headers=h)
    assert r.status_code==200 and r.json()['senses'][0]['examples']
    assert client.get('/v1/notebook',headers=h).json()['items']==[]

def test_dictionary_help_recorded_in_session_and_owner_checked(client,application):
    from test_backend import session
    h,user=register(client);other,_=register(client);s=session(client,application,h);svc=application.state.services
    id=s['view']['session_id'];row=svc.store.get('Session',id,user);data=copy.deepcopy(row['payload'])
    lesson=svc.store.get('LessonPackage',data['lesson_id'],user)['payload']
    data.update(phase='independent_application',task=copy.deepcopy(lesson['independent_task']))
    svc.store.put('Session',id,user,data,expected=row['version'])
    assert client.post('/v1/vocabulary/lookup',headers=other,json={'word':'available','session_id':id}).status_code==404
    r=client.post('/v1/vocabulary/lookup',headers=h,json={'word':'available','session_id':id})
    assert r.status_code==200,r.text
    current=client.get('/v1/sessions/'+id,headers=h).json()
    assert '查词释义' in current['view']['support_used']
    assert current['session_version']>s['session_version']
    assert client.get('/v1/profile',headers=h).json()['target_states']==[]
