"""V6 learning evidence, gradual assistance and guided task transitions."""
import copy
import hashlib
from difflib import SequenceMatcher
from .contracts import Task, DialogueResponse, TaskAttempt
from .store import uid, Missing, Conflict, digest
from .assessment import timestamp
from .providers import ReviewRequired, normalized

ROUND_NAMES=['换内容','接着对话','完成小任务']

class TeachingSupport:
    def __init__(self,sessions):
        self.sessions=sessions
        self.store=sessions.store;self.provider=sessions.provider;self.generator=sessions.generator
        self.curriculum=sessions.curriculum;self.settings=sessions.settings

    def actions(self,s):
        phase=s['phase'];task=s['task']
        if phase=='learning':return ['shadow','learn','next','request_translation','exit']
        if phase=='guided_feedback':return ['next','retry_guided','exit']
        if phase=='finished':return ['retry_guided','retry_independent','exit']
        if phase=='evaluating':return ['next' if s.get('evaluating_phase')=='supported_practice' else 'finish']
        if phase=='abandoned':return ['exit']
        actions=['speak','finish','exit']
        if phase=='supported_practice':return actions+['text_input','show_text','request_repeat','request_translation','request_hint','next']
        support=' '.join(task.get('allowed_support',[])).lower();policy=task.get('interaction_policy',{})
        for action,terms in [('request_repeat',['重复','重听','repeat']),('text_input',['文字练习','text_input']),
                             ('show_text',['显示文字','show_text']),('request_translation',['翻译','translation'])]:
            if policy.get(action,any(term in support for term in terms)):actions.append(action)
        return actions+['return_guided']

    def demo(self,s,lesson):
        if s['phase']!='learning':return []
        materials=lesson['learning_materials']
        assets={a['payload'].get('text'):a['payload'] for a in self.store.list('AudioAsset',s['owner'])}
        lines=[]
        for index,m in enumerate(materials):
            cue=m.get('partner_line') or (s['task']['opening'] if index==0 else '')
            if cue:
                lines.append({'speaker':'partner','text':cue,'audio_ref':assets.get(cue,{}).get('audio_ref'),
                              'meaning_zh':m.get('partner_meaning_zh','')})
            lines.append({'speaker':'learner','text':m['expression'],'meaning_zh':m.get('meaning_zh',''),
                          'audio_ref':m.get('audio_ref')})
        return lines

    async def prepare(self,s,owner,renew=False):
        if len(s.get('guided_tasks',[]))==3 and not renew:return
        lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
        target=self.curriculum.target(lesson['target_ids'][0],lesson['map_version'])
        feedback={'practice_focus':s.get('practice_focus','')} if s.get('practice_focus') else None
        for attempt in range(3):
            result=await self.provider.guided(lesson,target,s.get('guided_tasks',[])+[s['task']] if renew else [],feedback)
            try:
                parsed=self.validate_guided(result,s,lesson,renew)
                review=await self.provider.review_guided(parsed,target,lesson['learning_materials'])
                if review.get('decision')=='pass':break
                issues=review.get('reasons') or ['引导任务未通过语义审核']
            except (ReviewRequired,ValueError,TypeError,KeyError) as error:
                issues=[str(error)]
                review={'decision':'fail','reasons':issues}
            self.store.put('GuidedTaskReview',uid(),owner,{'session_id':s['session_id'],
                'attempt':attempt+1,'draft':result,'review':review,'recorded_at':timestamp()})
            feedback={'draft':result,'issues':issues}
        else:
            raise ReviewRequired('引导任务三次生成未通过审核，请重试；原学习进度已保留')
        for t in parsed:await self.generator.audio(t['opening'],owner,'partner_opening')
        s['guided_tasks']=parsed;s['guided_index']=0

    def validate_guided(self,result,s,lesson,renew):
        tasks=result.get('tasks',[])
        if len(tasks)!=3:raise ReviewRequired('引导练习需包含三轮任务')
        parsed=[]
        for index,task in enumerate(tasks):
            task.update(task_id=uid(),task_version=1)
            if renew and index==2:
                template=lesson['independent_task']
                task['assessment_contract']['critical_checks']=copy.deepcopy(template['assessment_contract']['critical_checks'])
                task['assessment_contract']['critical_meanings']=copy.deepcopy(template['assessment_contract'].get('critical_meanings',[]))
                task['allowed_support']=copy.deepcopy(template['allowed_support'])
                task['interaction_policy']=copy.deepcopy(template.get('interaction_policy',{}))
            t=Task.model_validate(task).model_dump()
            if not t['learner_prompt'] or not t['opening'] or not t['learner_facts'] or not t['partner_private_facts']:
                raise ReviewRequired('引导任务缺少具体条件')
            if not t['assessment_contract'].get('critical_checks'):raise ReviewRequired('缺少引导任务检查要求')
            own=set(t['learner_facts'].get('available_times',[]));partner=set(t['partner_private_facts'].get('available_times',[]))
            if own or partner:
                if not own&partner or set(t['assessment_contract'].get('acceptable_times',[]))!=own&partner:
                    raise ReviewRequired(f'第{index+1}轮时间条件矛盾：双方交集应为{sorted(own&partner)}，acceptable_times实际为{t["assessment_contract"].get("acceptable_times",[])}。把对方会拒绝的时间移出partner_private_facts.available_times，放入cannot_make_times；同步修正opening和role_rules。')
            previous=(s.get('guided_tasks') or [lesson['practice_task']])+[s['task']]
            if renew and any(t['learner_facts']==old['learner_facts'] and t['partner_private_facts']==old['partner_private_facts'] for old in previous):
                raise ReviewRequired('再练任务未更换内容')
            if index and t['learner_facts']==parsed[-1]['learner_facts'] and t['partner_private_facts']==parsed[-1]['partner_private_facts']:
                raise ReviewRequired('三轮引导任务条件重复')
            parsed.append(t)
        return parsed

    async def shadow(self,id,owner,request):
        row=self.store.get('Session',id,owner);s=copy.deepcopy(row['payload']);index=request['material_index']
        key=id+':'+request['input_id']
        try:
            saved=self.store.get('ShadowAttempt',key,owner)['payload']
            if saved['request_hash']!=digest(request):raise Conflict('跟读请求ID已被使用')
            if saved['can_continue'] and index not in {e['material_index'] for e in s['learning_events']}:
                self.sessions.learned(id,owner,index,saved['transcript'] or 'fixture shadow recording')
            return {'feedback':saved,'session':self.sessions.view(id,owner)}
        except Missing:pass
        if s['phase']!='learning':raise Conflict('当前不是跟读阶段')
        lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
        if not 0<=index<len(lesson['learning_materials']):raise ValueError('Invalid material index')
        asset=self.store.get('AudioAsset',request['audio_ref'].rsplit('/',1)[-1],owner)['payload']
        if asset['purpose']!='learner_recording':raise ValueError('Audio is not a learner recording')
        file=self.settings.media_dir/asset['filename'];data=file.read_bytes()
        if hashlib.sha256(data).hexdigest()!=asset['sha256']:raise ValueError('Audio asset changed')
        feedback={'request_hash':digest(request),'audio_ref':request['audio_ref'],'material_index':index,
                  'recorded_at':timestamp(),'fixture':self.provider.fixture or bool(asset.get('fixture')),'pronunciation':'not_assessed'}
        if self.provider.fixture:
            feedback.update(transcript='',can_continue=True,message='测试录音已收到；不评价发音或能力。')
        else:
            try:
                transcript=await self.provider.transcribe(data,asset['filename'])
                ratio=SequenceMatcher(None,normalized(lesson['learning_materials'][index]['expression']),normalized(transcript['text'])).ratio()
                feedback.update(transcript=transcript['text'],asr=transcript,can_continue=ratio>=.55,
                    message='已收到跟读。回听自己，与示范比较。' if ratio>=.55 else '识别内容与示范差异较大，请回听后重试。')
            except ReviewRequired:
                feedback.update(transcript='',can_continue=False,message='录音未能确认，请靠近麦克风重新录制。')
        s['shadow_feedback']=feedback
        if feedback['can_continue']:s['shadow_completed_indices']=sorted(set(s.get('shadow_completed_indices',[])+[index]))
        with self.store.transaction() as c:
            self.store.put('ShadowAttempt',key,owner,feedback,conn=c)
            self.store.put('Session',id,owner,s,expected=row['version'],conn=c)
        if feedback['can_continue']:
            # Exposure only. Shadowing never updates independent target mastery.
            self.sessions.learned(id,owner,index,feedback['transcript'] or 'fixture shadow recording')
        return {'feedback':feedback,'session':self.sessions.view(id,owner)}

    async def help(self,id,owner,entry,row,s):
        task=s['task'];kind=entry['type'];actions=self.actions(s)
        if kind not in actions:raise Conflict('本阶段合同不允许此项帮助')
        hint_content=None
        if kind=='request_repeat':
            source=entry.get('source_turn_id')
            turn=next((t for t in s['turns'] if t['turn_id']==source and t['speaker']=='partner'),None) if source else next((t for t in reversed(s['turns']) if t['speaker']=='partner'),None)
            if source and turn is None:raise ValueError('没有可重听的公开内容')
            text=turn['text'] if turn else task['opening']
            support=['请求重复'];audio=(await self.generator.audio(text,owner,'partner_response'))['audio_ref'];response_kind='repeat'
        elif kind=='request_translation':
            turn=next((t for t in s['turns'] if t['turn_id']==entry.get('source_turn_id') and t['speaker']=='partner'),None)
            source=turn['text'] if turn else None
            ref=entry.get('source_turn_id') or ''
            if s['phase']=='learning' and ref.startswith('material:'):
                lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
                try:source=lesson['learning_materials'][int(ref.split(':')[1])]['expression']
                except (ValueError,IndexError):raise ValueError('无效学习表达')
            if s['phase']=='learning' and ref=='demo:0':source=task['opening']
            if not source:raise ValueError('没有可翻译的公开内容')
            text=(await self.provider.translate(source)).get('text','');support=['查看翻译'];audio=None;response_kind='translation'
        else:
            lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
            target=self.curriculum.target(lesson['target_ids'][0],lesson['map_version'])
            level=entry['hint_level']
            hint=await self.provider.hint(task,s['turns'],lesson['learning_materials'],target,level)
            text=hint.get('text','');hint_content=hint.get('hint_content')
            support=[{'intent':'意图提示','pattern':'句型提示','example':'完整示例','learned':'所学表达'}[level]]
            audio=(await self.generator.audio(text,owner,'hint_example'))['audio_ref'] if level=='example' else None;response_kind='hint'
        if not isinstance(text,str) or not text.strip() or len(text)>2000:raise ReviewRequired('暂时没有可用帮助，请重试')
        response=DialogueResponse(session_id=id,task_id=task['task_id'],turn_id=uid(),reply_to=entry['input_id'],text='' if response_kind=='repeat' and 'show_text' not in actions else text,
                                  audio_ref=audio,support_provided=support,kind=response_kind,hint_content=hint_content).model_dump()
        s['support_used']=sorted(set(s['support_used']+support))
        s.setdefault('help_events',[]).append({'kind':kind,'support':support,'text':text,'recorded_at':timestamp(),
            'hint_level':entry['hint_level'] if response_kind=='hint' else None,
            'source_turn_id':s['turns'][-1]['turn_id'] if s['turns'] else None})
        s['request_responses'][entry['input_id']]={'hash':digest(entry),'response':response}
        self.store.put('Session',id,owner,s,expected=row['version'])
        return response

    def abandon(self,id,owner,s,conn):
        if s['phase'] not in ('supported_practice','independent_application'):return
        lesson=self.store.get('LessonPackage',s['lesson_id'],owner,conn)['payload'];task=s['task']
        aid=id+'/'+task['task_id']
        try:self.store.get('TaskAttempt',aid,owner,conn);return
        except Missing:pass
        attempt=TaskAttempt(attempt_id=aid,user_id=owner,session_id=id,lesson_id=s['lesson_id'],lesson_version=s['lesson_version'],
            map_version=lesson['map_version'],task_id=task['task_id'],task_version=task['task_version'],target_ids=lesson['target_ids'],
            phase=s['phase'],review_metadata=s.get('review_metadata',{}),status='abandoned',task_snapshot_ref=aid+'/snapshot',turns=s['turns'],support_used=s['support_used'],
            fixture=s['fixture'],started_at=s['started_at'],finished_at=timestamp()).model_dump()
        self.store.put('TaskAttempt',aid,owner,attempt,conn=conn);self.store.put('TaskSnapshot',aid+'/snapshot',owner,task,conn=conn)

    async def transition(self,id,owner,action,expected):
        row=self.store.get('Session',id,owner);s=copy.deepcopy(row['payload'])
        if row['version']!=expected:raise Conflict('Session changed')
        if action not in ('exit','return_guided','retry_guided','retry_independent'):raise ValueError('未知阶段操作')
        if s['phase']=='evaluating':raise Conflict('评价正在保存，请完成后再切换')
        if action!='exit':
            if action=='return_guided' and s['phase']!='independent_application':raise Conflict('当前不是独立应用')
            if action=='retry_guided' and s['phase'] not in ('guided_feedback','finished'):raise Conflict('当前不能重新练习')
            if action=='retry_independent' and s['phase']!='finished':raise Conflict('请先结束本次独立任务')
            updated=copy.deepcopy(s)
            try:
                result=self.store.get('AssessmentResult',id+'/'+s['task']['task_id'],owner)['payload']
                checks=result['target_results'][0]['checks']
                updated['practice_focus']=next((x['criterion'] for x in checks if x['result']=='not_met'),'')
            except Missing:updated['practice_focus']=''
            await self.prepare(updated,owner,renew=True)
            lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
            fresh=copy.deepcopy(updated['guided_tasks'][2])
            original=lesson['independent_task']
            # Same target contract, new concrete conditions, no worked-answer assistance.
            fresh['assessment_contract']['critical_checks']=original['assessment_contract']['critical_checks']
            fresh['assessment_contract']['critical_meanings']=original['assessment_contract'].get('critical_meanings',[])
            fresh['allowed_support']=copy.deepcopy(original['allowed_support'])
            fresh['interaction_policy']=copy.deepcopy(original.get('interaction_policy',{}))
            updated['next_independent_task']=fresh
            updated.setdefault('review_metadata',{})['transfer_validated']=False
            updated['review_metadata']['retention_eligible']=False
            direct=action=='retry_independent'
            updated.update(phase='independent_application' if direct else 'supported_practice',guided_start_index=1,guided_end_index=1,guided_index=1,remediation=True,task=copy.deepcopy(fresh if direct else updated['guided_tasks'][1]),turns=[],support_used=[],help_events=[],started_at=timestamp(),request_responses={})
            asset=await self.generator.audio(updated['task']['opening'],owner,'partner_opening')
            updated['turns']=[{'turn_id':uid(),'speaker':'partner','text':updated['task']['opening'],'audio_ref':asset['audio_ref']}]
        else:updated={**s,'phase':'abandoned' if s['phase']!='finished' else 'finished'}
        with self.store.transaction() as c:
            self.abandon(id,owner,s,c)
            self.store.put('Session',id,owner,updated,expected=row['version'],conn=c)
        return self.sessions.view(id,owner)
