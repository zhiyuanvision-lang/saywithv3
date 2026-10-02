"""Synthetic decision-layer tests. Does not test speech/LLM semantic extraction."""
import json,pathlib,copy
P=pathlib.Path(__file__).resolve().parent
SCENARIOS=[
 ('CONTACT','Meet a classmate; supplied identity is Lin', ['greet','introduce'], 'Hi, I’m Lin. Nice to meet you.','Hi.','Hi, I’m Wang.'),
 ('INFO','Confirm workshop information',['date','room'], 'Is it on Friday in room 204?','Is it on Friday?','So it is Thursday in room 204.'),
 ('DESCRIBE','Identify a missing bag',['colour','location'],'The blue bag is under the chair.','It is blue.','The red bag is under the chair.'),
 ('NEEDS','Explain a food restriction',['restriction','request'],'I cannot eat peanuts. Could I have a nut-free meal?','Could I have another meal?','Peanuts are fine for me.'),
 ('STORY','Tell a supplied event sequence',['order','resolution'],'I missed the bus, so I called a taxi and arrived on time.','I missed the bus.','I arrived before I missed the bus.'),
 ('EXPLAIN','Explain device instructions',['first_step','next_step'],'First plug it in, then hold the power button.','Plug it in.','Press the power button before plugging it in.'),
 ('REQUEST','Decline an invitation politely',['decline','reason'],'Thanks, but I cannot come because I am working.','I cannot come.','Great, I will be there.'),
 ('ARRANGE','Agree a feasible meeting',['feasible_time','location'],'Could we meet at four thirty in the library?','Could we meet at four thirty?','Let’s meet at six in the library.'),
 ('SERVICE','Resolve a wrong order',['problem','remedy'],'I ordered soup, but this is salad. Could you replace it?','This is the wrong order.','I ordered salad, and this salad is fine.'),
 ('COMPARE','Select a train under a supplied constraint',['comparison','selection'],'Train A costs less, and it arrives before nine, so I’ll take A.','Train A is cheaper.','I’ll take B even though it arrives after nine.'),
 ('OPINION','Give any opinion; supplied fact: park is quiet, cafe has loud music',['position','reason'],'I prefer the park because we can talk without loud music.','I prefer the park.','I prefer the cafe because it has no loud music.'),
 ('RELATE','Apologise for a damaged borrowed book; supplied fact: learner damaged it',['acknowledgement','apology'],'I’m sorry I damaged your book.','Your book is damaged.','I did not damage your book.'),
 ('COLLAB','Agree responsibilities',['my_role','partner_role'],'I’ll prepare the slides, and you can check the figures.','I’ll prepare the slides.','Neither of us will prepare the slides.'),
 ('REPAIR','Correct a misunderstood number',['signal','correction'],'Sorry, I said thirteen, not thirty.','Sorry, that is not right.','Yes, thirty is correct.'),
 ('LISTEN','Act on supplied directions',['direction','landmark'],'I’ll turn left after the bank.','I’ll go past the bank.','I’ll turn right after the bank.'),
 ('MEDIA','Relay a supplied announcement',['new_time','place'],'The flight now leaves at ten from gate seven.','It leaves at ten.','The flight leaves at nine from gate seven.'),
 ('PHONE','Leave an actionable message',['identity','request'],'This is Lin. Please call me back about tomorrow’s meeting.','This is Lin.','This is Wang calling to cancel next month’s meeting.'),
 ('MEDIATE','Relay a supplied change',['change','consequence'],'The museum is closed today, so we need to go tomorrow.','The museum is closed today.','The museum is open today, so let’s go now.')]
def decide(e):
 if not e['valid_input'] or e['answer_leaked'] or e['semantic_uncertain']:return 'unjudgeable'
 if e['critical_contradiction']:return 'fail'
 if e['answer_support'] or set(e['required'])-set(e['evidenced']):return 'partial'
 return 'pass'
def run():
 cases=[]
 for family,context,required,good,partial,bad in SCENARIOS:
  base={'valid_input':True,'answer_leaked':False,'semantic_uncertain':False,'critical_contradiction':False,'answer_support':False,'required':required,'evidenced':required}
  variants=[('success',good,{},'pass'),('missing_meaning',partial,{'evidenced':required[:1]},'partial'),('contradiction',bad,{'critical_contradiction':True},'fail'),('answer_support',good,{'answer_support':True},'partial'),('bad_audio',good,{'valid_input':False},'unjudgeable'),('role_leak',good,{'answer_leaked':True},'unjudgeable'),('uncertain_extractor',good,{'semantic_uncertain':True},'unjudgeable')]
  for name,utterance,changes,expected in variants:
   ev=copy.deepcopy(base);ev.update(changes)
   cases.append({'id':family+'.'+name,'family':family,'scenario':context,'learner_utterance':utterance,'evidence':ev,'expected':expected,'actual':decide(ev),'evidence_origin':'assistant_authored_fixture_not_actual_model_prediction'})
 # Test precedence: an invalid signal with apparent contradiction cannot justify failure.
 for family,_,req,good,_,_ in SCENARIOS:
  ev={'valid_input':False,'answer_leaked':False,'semantic_uncertain':False,'critical_contradiction':True,'answer_support':False,'required':req,'evidenced':[]}
  cases.append({'id':family+'.invalid_precedence','family':family,'evidence':ev,'expected':'unjudgeable','actual':decide(ev)})
 failed=[c['id'] for c in cases if c['actual']!=c['expected']]
 (P/'scoring_anchor_cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n')
 result={'status':'passed' if not failed else 'failed','cases':len(cases),'families':len(SCENARIOS),'failures':failed,'scope':'synthetic structured-evidence decision-layer consistency only','not_tested':['LLM semantic extraction','audio recognition','fluency','learner CEFR/GSE accuracy','learning gains'],'independent_review':False}
 (P/'calibration_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False));assert not failed
if __name__=='__main__':run()
