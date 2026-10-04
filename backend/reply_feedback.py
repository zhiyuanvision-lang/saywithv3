"""Formative language feedback; never evidence of mastery or a pronunciation score."""
import copy
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .store import Conflict, Missing
from sqlalchemy.exc import IntegrityError

class Phrase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expression: str = Field(min_length=1,max_length=120)
    meaning_zh: str = Field(min_length=1,max_length=100)

class ReplyAdvice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['clear','correction','alternative','uncertain']
    explanation_zh: str = Field(min_length=1,max_length=160)
    expression: str = Field(default='',max_length=300)
    meaning_zh: str = Field(default='',max_length=200)
    phrases: list[Phrase] = Field(default_factory=list,max_length=2)
    @model_validator(mode='after')
    def usable(self):
        if self.status in ('correction','alternative') and (not self.expression.strip() or not self.meaning_zh.strip()):
            raise ValueError('Advice requires an example and meaning')
        if self.status in ('clear','uncertain'):
            self.expression='';self.meaning_zh='';self.phrases=[]
        return self

class ReplyFeedback(ReplyAdvice):
    turn_id: str
    audio_ref: str | None = None

def cache_new_advice(store,cache_id,owner,advice):
    try:
        store.put('ReplyFeedback',cache_id,owner,advice)
        return advice
    except IntegrityError:
        # Another analysis/request won the insert. Reuse its immutable text.
        return store.get('ReplyFeedback',cache_id,owner)['payload']


def cache_advice_audio(store,cache_id,owner,audio_ref):
    for attempt in range(3):
        row=store.get('ReplyFeedback',cache_id,owner)
        advice=copy.deepcopy(row['payload'])
        if advice.get('audio_ref'):return advice
        advice['audio_ref']=audio_ref
        try:
            store.put('ReplyFeedback',cache_id,owner,advice,expected=row['version'])
            return advice
        except Conflict:
            if attempt==2:raise


async def analyze_reply(sessions,id,owner,s,turn):
    from .providers import ProviderFailure, ReviewRequired
    from httpx import HTTPError
    from pydantic import ValidationError
    public_task={k:s['task'].get(k) for k in ('learner_facts','learner_prompt','learner_role')}
    try:
        advice=ReplyAdvice.model_validate(await sessions.provider.reply_advice(public_task,s['turns'])).model_dump()
        advice.update(turn_id=turn['turn_id'],audio_ref=None)
        cache_new_advice(sessions.store,id+'/'+turn['turn_id'],owner,advice)
    except (ProviderFailure,ReviewRequired,ValidationError,HTTPError):
        # Formative feedback failure must not prevent the conversation from continuing.
        return

async def reply_feedback(sessions,id,owner,turn_id):
    s=sessions.store.get('Session',id,owner)['payload']
    if s['phase'] not in ('supported_practice','guided_feedback','finished'):
        raise Conflict('请完成独立交流后再查看表达建议')
    turn=next((t for t in s['turns'] if t['turn_id']==turn_id and t['speaker']=='learner'),None)
    if turn is None:raise Missing('回答不存在')
    cache_id=id+'/'+turn_id
    try:advice=sessions.store.get('ReplyFeedback',cache_id,owner)['payload']
    except Missing:
        # Only public facts and preceding dialogue: never expose private answers.
        preceding=s['turns'][:s['turns'].index(turn)+1]
        public_task={k:s['task'].get(k) for k in ('learner_facts','learner_prompt','learner_role')}
        advice=ReplyAdvice.model_validate(await sessions.provider.reply_advice(public_task,preceding)).model_dump()
        advice.update(audio_ref=None,turn_id=turn_id)
        advice=cache_new_advice(sessions.store,cache_id,owner,advice)
    if advice['expression'] and not advice.get('audio_ref'):
        asset=await sessions.generator.audio(advice['expression'],owner,'partner_response')
        advice=cache_advice_audio(sessions.store,cache_id,owner,asset['audio_ref'])
    # Viewing a worked answer during practice is actual support, even on cache hits.
    if s['phase']=='supported_practice' and advice['expression']:
        row=sessions.store.get('Session',id,owner);updated=copy.deepcopy(row['payload'])
        if updated['phase']!='supported_practice' or updated['task']['task_id']!=s['task']['task_id']:
            raise Conflict('任务已切换，请重新查看')
        label='回答示范'
        if label not in updated['support_used']:
            updated['support_used'].append(label)
            updated.setdefault('help_events',[]).append({'kind':'reply_feedback','turn_id':turn_id})
            sessions.store.put('Session',id,owner,updated,expected=row['version'])
    return advice
