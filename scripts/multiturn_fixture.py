"""Deterministic two-expression fixture for UI tests; never generates mastery evidence.
Run with PYTHONPATH=. and isolated SAYWITH_DATABASE_URL/SAYWITH_MEDIA_DIR.
Start API first, then a second process with --worker.
"""
import asyncio,copy,os,uvicorn
from backend.app import create_app
from backend.config import Settings
from backend.providers import FixtureProvider
class TwoExpressions(FixtureProvider):
 async def generate(self,*args,**kwargs):
  lesson=await super().generate(*args,**kwargs)
  first=lesson['learning_materials'][0]
  first.update(partner_line=lesson['practice_task']['opening'],partner_meaning_zh='我三点没空。')
  second=copy.deepcopy(first)
  second.update(expression='Four thirty works for me.',hint_pattern='___ works for me.',meaning_zh='四点半对我合适。',intent_zh='确认安排',resource_id='confirm',partner_line='Four thirty is fine. Shall we meet at the court?',partner_meaning_zh='四点半可以。在球场见好吗？')
  lesson['learning_materials'].append(second)
  return lesson
 async def transcribe(self,*args):return {'text':'How about four?','quality':'fixture'}
 async def reply_advice(self,*args):return {'status':'clear','explanation_zh':'表达清楚，可以继续交流。','expression':'','meaning_zh':'','phrases':[]}
settings=Settings()
async def worker():
 app=create_app(settings,TwoExpressions(settings.workspace))
 while True:
  if not await app.state.services.generator.run_one('multiturn-ui-fixture'):await asyncio.sleep(.2)

if __name__=='__main__':
 import sys
 if '--worker' in sys.argv:asyncio.run(worker())
 else:uvicorn.run(create_app(settings,TwoExpressions(settings.workspace)),host='127.0.0.1',port=18105)
