"""Brief form explanation, supported output, then faded retrieval; never mastery evidence."""
import copy
import hashlib
import time
import re
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .store import Conflict,Missing,digest
from .assessment import timestamp
from .providers import ReviewRequired

def chinese_reason(text):
    text=re.sub(r"[A-Za-z]+(?:[ '’\-][A-Za-z]+)*",'',text or '')
    return text.replace('“”','').replace('""','').strip(' ，,；;')

def pack_boundary_ambiguous(text,material,prompt=''):
    # An imperative-looking 'Unpack' can be a fused 'I pack'. Never rewrite it.
    return bool(('打包' in prompt or re.search(r'\bI\s+pack\b',material.get('expression',''),re.I)) and
                re.search(r'(?:^|[.!?]\s*)unpack\b',text,re.I))

class LearningPlan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    usage_zh:str=Field(min_length=1,max_length=200)
    pattern:str=Field(min_length=1,max_length=160)
    supported_prompt_zh:str=Field(min_length=1,max_length=160)
    recall_prompts_zh:list[str]=Field(min_length=2,max_length=2)
    @model_validator(mode='after')
    def distinct_cues(self):
        cues=[self.supported_prompt_zh]+self.recall_prompts_zh
        if any(not c.strip() or len(c)>160 or re.search('[A-Za-z]',c) for c in cues):
            raise ValueError('Prompts must be short Chinese communicative intentions without English answers')
        for cue in cues:
            if not re.fullmatch(r'情境：[^\n]+\n轮到你：[^\n]+',cue.strip()):
                raise ValueError('Each cue needs two short Chinese lines: 情境：concrete public facts, then 轮到你：one specific speaking intention')
        if len(set(c.strip() for c in cues))!=3:raise ValueError('Use three different concrete conditions')
        return self

class LearningJudgement(BaseModel):
    model_config=ConfigDict(extra='forbid')
    met:bool
    confidence:Literal['high','low']
    explanation_zh:str=Field(min_length=1,max_length=180)
    reason_zh:str=Field(default='',max_length=180)
    better_expression:str=Field(default='',max_length=300)
    meaning_zh:str=Field(default='',max_length=200)

class LearningPracticeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    material_index:int=Field(ge=0)
    action:Literal['prepare','start','recall','show_pattern','show_example','attempt','shadow']
    expected_session_version:int|None=None
    input_id:str|None=Field(default=None,min_length=1,max_length=100)
    audio_ref:str|None=None
    stage:Literal['supported','recall']|None=None
    recognition_retry:bool=False
    confirmed_transcript:str|None=Field(default=None,min_length=1,max_length=1000)
    original_transcript:str|None=Field(default=None,min_length=1,max_length=1000)

class LearningPracticeService:
    def __init__(self,sessions):self.sessions=sessions

    async def worked_example(self,material,practice,prompt,owner):
        provider=self.sessions.provider
        example=practice.get('recovery_example') if practice.get('recovery_example_prompt')==prompt else None
        checked=practice.get('checked_example_prompt')==prompt
        repair=None
        for attempt in range(2):
            if not example:
                source={**material,'worked_example_feedback':repair} if repair else material
                judgement=LearningJudgement.model_validate(await provider.learning_judgement(source,prompt,''))
                example={'expression':judgement.better_expression,'meaning_zh':judgement.meaning_zh}
            if not example['expression'] or not example['meaning_zh']:
                repair='示范必须提供完整英文回答及其中文意思。'
            elif checked or not hasattr(provider,'review_learning_example'):
                break
            else:
                review=await provider.review_learning_example(prompt,example)
                if review.get('decision')=='pass':break
                repair=str(review.get('reasons') or ['示范与当前提示不对应'])[:1000]
            example=None;checked=False
        else:raise ReviewRequired('示范与本次练习尚未对应，请重试；原进度已保留')
        if not example.get('audio_ref'):
            asset=await self.sessions.generator.audio(example['expression'],owner,'partner_response')
            example['audio_ref']=asset['audio_ref']
        practice.update(recovery_example=example,recovery_example_prompt=prompt,checked_example_prompt=prompt)
        return example

    def view(self,s):
        index=s.get('learning_practice_index',0)
        practice=s.get('learning_practices',{}).get(str(index))
        if not practice:return None
        public={k:copy.deepcopy(practice[k]) for k in ('material_index','stage','usage_zh','pattern','feedback') if k in practice}
        if practice.get('previous_feedback'):public['previous_feedback']=copy.deepcopy(practice['previous_feedback'])
        # Only show the relevant cue. Recall screens never include the supported frame.
        if practice['stage']=='recall' or practice.get('help_used'):
            public['prompt_zh']=practice['recall_prompts_zh'][practice.get('recall_index',0)]
        else:public['prompt_zh']=practice['supported_prompt_zh']
        if practice['stage']=='recall':public['pattern']=''
        if practice.get('help_used') and practice['stage']=='supported':
            public['example']=practice.get('recovery_example') if practice.get('checked_example_prompt')==public['prompt_zh'] else None
        return public

    def advance_supported(self,practice):
        feedback=practice.get('feedback') or {}
        if practice['stage']!='supported' or not feedback.get('met') or feedback.get('confidence')!='high':return
        practice['previous_feedback']=copy.deepcopy(feedback)
        if practice.get('help_used'):practice['recall_index']=(practice.get('recall_index',0)+1)%2
        practice.update(stage='recall',feedback=None,help_used=False)

    async def act(self,id,owner,data):
        request=LearningPracticeRequest.model_validate(data).model_dump()
        for optional in ('confirmed_transcript','original_transcript'):
            if request[optional] is None:request.pop(optional)
        store=self.sessions.store;row=store.get('Session',id,owner);s=copy.deepcopy(row['payload'])
        index=request['material_index'];key=str(index);action=request['action']
        receipt_id=id+'/'+str(request.get('input_id'))
        if action in ('attempt','shadow'):
            if not request['input_id'] or not request['audio_ref']:raise ValueError('请提交录音和请求ID')
            try:
                receipt=store.get('LearningPracticeAttempt',receipt_id,owner)['payload']
                if receipt['request_hash']!=digest(request):raise Conflict('录音请求ID已被使用')
                if action=='attempt' and receipt['stage']=='recall' and receipt['feedback']['met'] and s['phase']=='learning' and index not in {e['material_index'] for e in s['learning_events']}:
                    self.sessions.learned(id,owner,index,receipt['feedback']['transcript'])
                return self.sessions.view(id,owner)
            except Missing:pass
        if s['phase']!='learning':raise Conflict('当前不是学习阶段')
        lesson=store.get('LessonPackage',s['lesson_id'],owner)['payload']
        if not 0<=index<len(lesson['learning_materials']):raise ValueError('Invalid material index')
        if any(not p['completed'] for p in self.sessions.lexical.view(s,lesson)):
            raise Conflict('请先完成本课生词尝试')
        if request['expected_session_version'] is not None and request['expected_session_version']!=row['version']:
            raise Conflict('学习进度已更新，请重新获取')
        material=lesson['learning_materials'][index]
        practices=s.setdefault('learning_practices',{})
        existing=practices.get(key)
        refresh=bool(action=='prepare' and existing and existing.get('plan_version')!=4
                     and existing.get('stage')!='complete' and not existing.get('feedback') and not existing.get('help_used'))
        if key not in practices or refresh:
            if action!='prepare':raise Conflict('请先准备本次表达练习')
            repair=None
            for attempt in range(2):
                try:
                    candidate=material.get('learning_plan') if attempt==0 else None
                    if not candidate:candidate=await self.sessions.provider.learning_plan(material,repair)
                    plan=LearningPlan.model_validate(candidate).model_dump()
                    if hasattr(self.sessions.provider,'review_learning_plan'):
                        review=await self.sessions.provider.review_learning_plan(material,plan)
                        if review.get('decision')!='pass':raise ValueError(str(review.get('reasons') or ['练习必须改变示范条件，并保持原沟通目标']))
                    break
                except ValueError as error:
                    repair=str(error)[:1000]
                    if attempt==1:raise ReviewRequired('表达练习条件未通过检查，请重新准备') from error
            practices[key]={**plan,'plan_version':4,'material_index':index,
                            'stage':existing['stage'] if refresh else 'preview',
                            'recall_index':existing.get('recall_index',0) if refresh else 0,
                            'feedback':None,'help_used':False}
            if refresh and existing.get('previous_feedback'):
                practices[key]['previous_feedback']=copy.deepcopy(existing['previous_feedback'])
            s['active_learning']=True
        practice=practices[key];s['learning_practice_index']=index
        if action=='prepare':
            feedback=practice.get('feedback') or {}
            if practice['stage']=='complete' and feedback.get('met') and not feedback.get('fixture') and not feedback.get('better_expression'):
                # Backfill feedback for already-completed attempts without changing the
                # original transcript, success decision, or learning evidence.
                prompt=practice['recall_prompts_zh'][practice.get('recall_index',0)]
                correction=LearningJudgement.model_validate(await self.sessions.provider.learning_judgement(material,prompt,feedback['transcript']))
                if correction.better_expression and correction.meaning_zh:
                    feedback.update(better_expression=correction.better_expression,meaning_zh=correction.meaning_zh)
            self.advance_supported(practice)
            if practice['stage']=='supported' and practice.get('help_used') and practice.get('recovery_example'):
                prompt=practice['recall_prompts_zh'][practice.get('recall_index',0)]
                await self.worked_example(material,practice,prompt,owner)
            if row['payload']==s:return self.sessions.view(id,owner)
        elif action=='start':
            if practice['stage']!='preview':raise Conflict('当前不能开始有提示表达')
            practice.update(stage='supported',feedback=None)
        elif action=='recall':
            if practice['stage']=='recall' and practice.get('previous_feedback'):
                return self.sessions.view(id,owner)
            if practice['stage'] not in ('preview','supported'):raise Conflict('当前不能进入脱离示范练习')
            if practice['stage']=='supported' and not (practice.get('feedback') or {}).get('met'):
                raise Conflict('请先完成一次有提示表达')
            if practice.get('help_used'):practice['recall_index']=(practice.get('recall_index',0)+1)%2
            practice.update(stage='recall',feedback=None,help_used=False)
        elif action=='show_pattern':
            if practice['stage']!='recall':raise Conflict('当前不是脱离示范练习')
            practice.update(stage='supported',feedback=None,help_used=True)
            s.setdefault('learning_help_events',[]).append({'material_index':index,'kind':'revealed_pattern','time':timestamp()})
        elif action=='show_example':
            if practice['stage'] not in ('recall','supported'):raise Conflict('当前不能查看示范')
            prompt=practice['recall_prompts_zh'][practice.get('recall_index',0)] if practice['stage']=='recall' or practice.get('help_used') else practice['supported_prompt_zh']
            await self.worked_example(material,practice,prompt,owner)
            if practice['stage']=='supported' and not practice.get('help_used'):
                practice['recall_prompts_zh'][practice.get('recall_index',0)]=prompt
            practice.update(stage='supported',feedback=None,help_used=True)
            s.setdefault('learning_help_events',[]).append({'material_index':index,'kind':'revealed_example','time':timestamp()})
        else:
            if action=='attempt' and request['stage']!=practice['stage']:raise Conflict('录音与当前练习步骤不一致')
            if action=='attempt' and practice['stage'] not in ('supported','recall'):raise Conflict('当前不能提交表达')
            asset=store.get('AudioAsset',request['audio_ref'].rsplit('/',1)[-1],owner)['payload']
            if asset['purpose']!='learner_recording':raise ValueError('请提交自己的录音')
            audio=(self.sessions.settings.media_dir/asset['filename']).read_bytes()
            if hashlib.sha256(audio).hexdigest()!=asset['sha256']:raise ValueError('录音校验失败')
            confirmed=request.get('confirmed_transcript')
            if confirmed is not None:
                previous=practice.get('feedback') or {}
                if action!='attempt' or request['recognition_retry'] or not confirmed.strip():raise ValueError('请确认实际说出的文字')
                if previous.get('audio_ref')!=request['audio_ref'] or previous.get('transcript')!=request['original_transcript']:
                    raise Conflict('录音或识别文字已更新，请重新确认')
            try:
                progress_row=store.get('InputProgress',receipt_id,owner)
                progress=progress_row['payload'];progress_version=progress_row['version']
                if progress['request_hash']!=digest(request):raise Conflict('录音请求ID已被使用')
            except Missing:
                progress={'schema_version':'1.0','session_id':id,'input_id':request['input_id'],'turn_id':request['input_id'],
                          'status':'recognizing','audio_ref':request['audio_ref'],'request_hash':digest(request),'started_at':time.time()}
                progress_version=store.put('InputProgress',receipt_id,owner,progress)
            if self.sessions.provider.fixture:
                transcript={'text':'测试录音','quality':'final_transcript_available'}
                judgement=LearningJudgement(met=True,confidence='high',explanation_zh='测试录音已收到；测试模式不评价表达或能力。')
            else:
                try:
                    transcript=progress.get('asr')
                    if not transcript:
                        provider=self.sessions.provider
                        if confirmed is not None:
                            transcript={'text':confirmed.strip(),'quality':'final_transcript_available','source':'learner_confirmed',
                                        'original_transcript':request['original_transcript']}
                        elif request['recognition_retry'] and hasattr(provider,'transcribe_learning'):
                            transcript=await provider.transcribe_learning(audio,asset['filename'],material)
                        else:transcript=await provider.transcribe(audio,asset['filename'])
                except ReviewRequired:transcript={'text':'','quality':'unavailable'}
                progress.update(status='responding',transcript=transcript.get('text',''),asr=transcript,recognized_at=time.time())
                progress_version=store.put('InputProgress',receipt_id,owner,progress,expected=progress_version)
                if not transcript.get('text','').strip() or transcript.get('quality')!='final_transcript_available':
                    judgement=LearningJudgement(met=False,confidence='low',explanation_zh='录音没有听清，请回听后重新说一次。')
                elif action=='shadow':
                    judgement=LearningJudgement(met=False,confidence='low',explanation_zh='录音已收到。接下来换成自己的内容说。')
                elif confirmed is None and pack_boundary_ambiguous(transcript['text'],material,
                        practice['recall_prompts_zh'][practice['recall_index']] if practice['stage']=='recall' or practice.get('help_used') else practice['supported_prompt_zh']):
                    judgement=LearningJudgement(met=False,confidence='low',explanation_zh='录音中“我打包”和“拆包”的识别存在歧义。请回听并更正识别文字，暂不判断表达是否有误。')
                else:
                    prompt=practice['recall_prompts_zh'][practice['recall_index']] if practice['stage']=='recall' or practice.get('help_used') else practice['supported_prompt_zh']
                    judgement=LearningJudgement.model_validate(await self.sessions.provider.learning_judgement(material,prompt,transcript['text']))
            if self.sessions.provider.fixture:
                progress.update(status='responding',transcript=transcript['text'],asr=transcript,recognized_at=time.time())
                progress_version=store.put('InputProgress',receipt_id,owner,progress,expected=progress_version)
            feedback={**judgement.model_dump(),'met':judgement.met and judgement.confidence=='high',
                      'transcript':transcript['text'],'audio_ref':request['audio_ref'],'fixture':self.sessions.provider.fixture}
            if confirmed is not None:
                feedback.update(transcript_source='learner_confirmed',original_transcript=request['original_transcript'])
            if not feedback['met'] and chinese_reason(judgement.reason_zh):
                feedback['explanation_zh']=chinese_reason(judgement.reason_zh)
            if action=='shadow':feedback['met']=False
            if practice['stage']=='recall':
                practice['recovery_example']={'expression':judgement.better_expression,'meaning_zh':judgement.meaning_zh} if judgement.better_expression and judgement.meaning_zh else None
                practice['recovery_example_prompt']=practice['recall_prompts_zh'][practice['recall_index']]
                practice.pop('checked_example_prompt',None)
                # Keep failed retrieval answer-free. Help must be an explicit action.
                if not feedback['met']:
                    feedback['better_expression']='';feedback['meaning_zh']=''
                if not feedback['met'] and re.search('[A-Za-z]',feedback['explanation_zh']):
                    reason=chinese_reason(judgement.reason_zh)
                    if not reason or re.search('[A-Za-z]',reason):
                        reason='；'.join(c.strip() for c in re.split('[，,。;；]',feedback['explanation_zh']) if c.strip() and not re.search('[A-Za-z]',c))
                    feedback['explanation_zh']=reason or '按当前识别文字，尚未能确认表达符合要求。请先回听并检查识别文字。'
            practice['feedback']=feedback
            if action=='attempt' and feedback['met']:
                if practice['stage']=='recall':practice['stage']='complete'
                elif practice['stage']=='supported':self.advance_supported(practice)
            receipt={'request_hash':digest(request),'material_index':index,'stage':request['stage'],
                     'feedback':feedback,'recorded_at':timestamp(),'help_used':practice.get('help_used',False)}
            with store.transaction() as c:
                progress.update(status='completed',completed_at=time.time())
                store.put('InputProgress',receipt_id,owner,progress,expected=progress_version,conn=c)
                store.put('LearningPracticeAttempt',receipt_id,owner,receipt,conn=c)
                store.put('Session',id,owner,s,expected=row['version'],conn=c)
            if practice['stage']=='complete' and index not in {e['material_index'] for e in s['learning_events']}:
                # This is exposure/initial retrieval only, never independent mastery.
                self.sessions.learned(id,owner,index,transcript['text'])
            return self.sessions.view(id,owner)
        store.put('Session',id,owner,s,expected=row['version'])
        return self.sessions.view(id,owner)
