import asyncio
import copy
import pytest
from backend.lesson_policy import lesson_policy,policy_issues
from backend.providers import APIProvider
from backend.config import Settings
from test_backend import application,client,register,generate,send
from test_v6_teaching import upload,next_round

@pytest.mark.parametrize('stage,minutes,count',[('Pre-A1',10,1),('A2',5,1),('A1',10,2),('A2',10,2),('B1',12,3),('C2',30,3)])
def test_load_accounts_for_faded_recall(stage,minutes,count):
    p=lesson_policy(stage,minutes,'consolidation',['known'])
    assert p['material_count']==count and p['new_expression_max']==count
    assert p['prefer_review'] and p['turn_budget_is_soft']

def bundle(lesson):
    lesson=copy.deepcopy(lesson)
    second=copy.deepcopy(lesson['learning_materials'][0]);second.update(expression='Four thirty works for me.',hint_pattern='___ works for me.',meaning_zh='四点半对我合适。',intent_zh='确认安排',resource_id='expr-confirm')
    lesson['learning_materials'][0].update(partner_line=lesson['practice_task']['opening'],partner_meaning_zh='我三点没空。')
    second.update(partner_line='That works for me. Shall we meet at the court?',partner_meaning_zh='可以。在球场见好吗？')
    lesson['learning_materials'].append(second)
    for name in ('practice_task','independent_task'):
        lesson[name]['assessment_contract']['dialogue_flow']=['提出替代时间','回应并确认安排']
    return lesson

def test_quality_gate_rejects_atomic_and_duplicate_materials(client,application):
    h,owner=register(client);job=generate(client,application,h)
    svc=application.state.services
    original=svc.store.get('LessonPackage',job['result_lesson_id'],owner)['payload']
    original['provenance']['fixture']=False
    policy=lesson_policy('A2',10,'new',[])
    assert policy_issues(original,policy)
    good=bundle(original);assert policy_issues(good,policy)==[]
    good['learning_materials'][1]['hint_pattern']=good['learning_materials'][0]['hint_pattern']
    assert any('重复' in x for x in policy_issues(good,policy))

def test_two_materials_dialogue_advice_and_independent_loop(client,application):
    h,owner=register(client);job=generate(client,application,h);svc=application.state.services
    row=svc.store.get('LessonPackage',job['result_lesson_id'],owner)
    lesson=bundle(row['payload']);svc.store.put('LessonPackage',job['result_lesson_id'],owner,lesson,expected=row['version'])
    r=client.post('/v1/sessions',headers=h,json={'lesson_id':job['result_lesson_id']});assert r.status_code==201
    s=r.json();sid=s['view']['session_id']
    assert len(s['view']['materials'])==2
    assert [x['speaker'] for x in s['view']['demonstration']]==['partner','learner','partner','learner']
    for index in range(2):
        r=client.post('/v1/sessions/'+sid+'/shadow',headers=h,json={'material_index':index,'audio_ref':upload(client,h),'input_id':f'shadow-{index}'})
        assert r.status_code==200,r.text
        s=r.json()['session']
        if index==0:
            assert client.post('/v1/sessions/'+sid+'/next',headers=h,json={'expected_session_version':s['session_version'],'advance_round':True}).status_code==409
    s=next_round(client,h,s)
    for round in range(3):
        for index,text in enumerate(['How about three?','Three works for me.']):
            r=send(client,h,s,text=text,input_id=f'{round}-{index}');assert r.status_code==200,r.text
            s=client.get('/v1/sessions/'+sid,headers=h).json()
        learners=[t for t in s['turns'] if t['speaker']=='learner'];assert len(learners)==2
        advice=client.post('/v1/sessions/'+sid+'/turns/'+learners[-1]['turn_id']+'/feedback',headers=h)
        assert advice.status_code==200,advice.text
        assert client.get('/v1/profile',headers=h).json()['target_states']==[]
        s=next_round(client,h,s)
    assert s['view']['phase']=='guided_feedback'
    s=next_round(client,h,s);assert s['view']['phase']=='independent_application'
    assert client.post('/v1/sessions/'+sid+'/turns/'+learners[-1]['turn_id']+'/feedback',headers=h).status_code==409
    assert send(client,h,s,text='How about two?',input_id='independent').status_code==200
    assert client.post('/v1/sessions/'+sid+'/finish',headers=h).status_code==200
    assert client.get('/v1/sessions/'+sid,headers=h).json()['view']['phase']=='finished'
    assert client.get('/v1/profile',headers=h).json()['target_states']==[] # Fixtures never certify mastery.


def test_generator_passes_exact_count_and_partner_keeps_tutor_separate():
    p=APIProvider(Settings())
    seen=[]
    async def capture(prompt,data,*args):seen.append((prompt,data));return {}
    p.json=capture
    policy=lesson_policy('A2',10,'new',[])
    asyncio.run(p.generate({'difficulty':{'new_expression_limit':2},'resource_plan':{'speaking_plan':policy}},{}))
    schema=seen[-1][1]['output_schema']['properties']['learning_materials']
    assert schema['minItems']==schema['maxItems']==2
    asyncio.run(p.dialogue({},[],{'outcome':'test'},'supported_practice'))
    assert 'never manufacture conflict' in seen[-1][0] and 'tutor corrections' in seen[-1][0]

def test_reuse_budget_accepts_new_values_but_not_all_new_frames():
    policy=lesson_policy('A2',10,'consolidation',[],[{'expression':'How about five?','hint_pattern':'How about ___?'}])
    assert policy['minimum_reuse']==1 and policy['new_expression_max']==1
    assert not policy['reuse_is_mastery_evidence']
    sample={'learning_materials':[{'expression':'How about six?','hint_pattern':'How about ___?','partner_line':'Not at five.','partner_meaning_zh':'五点不行。'},{'expression':'Six works.','hint_pattern':'___ works.','partner_line':'Six is fine.','partner_meaning_zh':'六点可以。'}], 'practice_task':{'opening':'Not at five.','assessment_contract':{'dialogue_flow':['建议','确认']}},'independent_task':{'assessment_contract':{'dialogue_flow':['建议','确认']}}}
    assert not policy_issues(sample,policy)
    sample['learning_materials'][0]['hint_pattern']='Can we meet ___?'
    assert any('复用' in issue for issue in policy_issues(sample,policy))
