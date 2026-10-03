"""Server-controlled phase, role state, private facts and actual support tracking."""
import copy
import time
from .contracts import LearnerLessonView, DialogueResponse, LearnerInput, TaskAttempt
from .store import uid, Conflict, Missing, digest
from .assessment import timestamp
from .providers import ReviewRequired

PHASES=['learning','supported_practice','independent_application','finished']

class Sessions:
    def __init__(self,store,curriculum,provider,generator,assessor,settings):
        self.store=store;self.curriculum=curriculum;self.provider=provider;self.generator=generator;self.assessor=assessor;self.settings=settings

    def create(self,owner,lesson_id):
        lesson=self.store.get('LessonPackage',lesson_id,owner)['payload']
        fixture=bool(lesson['provenance'].get('fixture'))
        if not lesson['learner_ready'] and not (self.settings.mode=='fixture' and fixture):raise Conflict('课程尚未通过发布审核')
        id=uid();session={'session_id':id,'lesson_id':lesson_id,'lesson_version':lesson['lesson_version'],
            'phase':'learning','fixture':fixture,'task':copy.deepcopy(lesson['practice_task']),
            'turns':[],'support_used':[],'started_at':timestamp(),'learning_events':[],'finished_attempts':[],
            'request_responses':{}}
        self.store.put('Session',id,owner,session)
        return self.view(id,owner)

    def view(self,id,owner):
        row=self.store.get('Session',id,owner);s=row['payload'];lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
        task=s['task'];phase=s['phase']
        # Only explicit projection fields are emitted; private facts/criteria remain server-side.
        view=LearnerLessonView(session_id=id,lesson_id=s['lesson_id'],lesson_version=s['lesson_version'],
            task_id=task['task_id'],phase=phase,instruction=task['learner_prompt'] if phase!='learning' else '理解说法，换成自己的内容，然后遮住答案试说。',
            learner_facts=task['learner_facts'] if phase!='learning' else {},fixture=s['fixture'],
            available_actions=(['learn','next'] if phase=='learning' else ['speak','request_repeat','finish']+(['request_hint'] if phase=='supported_practice' else [])) if phase not in ('finished','evaluating') else (['next'] if phase=='evaluating' and s.get('evaluating_phase')=='supported_practice' else ['finish'] if phase=='evaluating' else []),
            materials=lesson['learning_materials'] if phase=='learning' else [],
            completed_material_indices=sorted({e['material_index'] for e in s['learning_events']})).model_dump()
        return {'view':view,'session_version':row['version'],'turns':[{k:t[k] for k in ('turn_id','speaker','text','transcript','audio_ref') if k in t} for t in s['turns']]}

    def learned(self,id,owner,index,personal_text):
        row=self.store.get('Session',id,owner);s=copy.deepcopy(row['payload'])
        if s['phase']!='learning':raise Conflict('当前不是学习阶段')
        lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
        if not 0<=index<len(lesson['learning_materials']):raise ValueError('Invalid material index')
        if not personal_text.strip():raise ValueError('请先替换为自己的表达')
        s['learning_events'].append({'material_index':index,'personal_text':personal_text[:1000],'time':timestamp()})
        # Exposure is recorded; user assertions do not grant mastery.
        with self.store.transaction() as c:
            profile_row=self.store.get('LearnerProfile',owner,owner,c);profile=copy.deepcopy(profile_row['payload'])
            resource_id=lesson['learning_materials'][index]['resource_id']
            if resource_id:
                resources={r['resource_id']:r for r in profile['resource_states']}
                resource=resources.setdefault(resource_id,{'resource_id':resource_id,'understanding':'not_checked','retrieval':'not_checked'})
                resource['introduced']=True;resource['last_exposure']=timestamp()
                resource['learning_event_refs']=resource.get('learning_event_refs',[])+[id+':'+str(index)]
                profile['resource_states']=list(resources.values());profile['profile_version']+=1
                self.store.put('LearnerProfile',owner,owner,profile,expected=profile_row['version'],conn=c)
            self.store.put('Session',id,owner,s,expected=row['version'],conn=c)
        return self.view(id,owner)

    async def next(self,id,owner,expected):
        row=self.store.get('Session',id,owner);s=copy.deepcopy(row['payload'])
        if row['version']!=expected:raise Conflict('Session changed')
        if s['phase']=='learning':
            lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
            done={e['material_index'] for e in s['learning_events']}
            if len(done)<len(lesson['learning_materials']):raise Conflict('请先完成表达替换和遮答案试说')
            s['phase']='supported_practice'
        elif s['phase']=='supported_practice' or (s['phase']=='evaluating' and s.get('evaluating_phase')=='supported_practice'):
            if not any(t['speaker']=='learner' for t in s['turns']):raise Conflict('请先完成一次有提示练习')
            await self.finish_attempt(id,owner)
            row=self.store.get('Session',id,owner);s=copy.deepcopy(row['payload'])
            lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
            s.update(phase='independent_application',task=copy.deepcopy(lesson['independent_task']),turns=[],support_used=[],started_at=timestamp(),request_responses={})
        else:raise Conflict('无法进入下一阶段')
        asset=next((x for x in self.store.list('AudioAsset',owner) if x['payload'].get('text')==s['task']['opening']),None)
        s['turns']=[{'turn_id':uid(),'speaker':'partner','text':s['task']['opening'],
                     'audio_ref':asset['payload']['audio_ref'] if asset else None}]
        self.store.put('Session',id,owner,s,expected=row['version'])
        return self.view(id,owner)

    async def input(self,id,owner,data):
        entry=LearnerInput.model_validate(data).model_dump()
        row=self.store.get('Session',id,owner);s=copy.deepcopy(row['payload'])
        key=entry['input_id'];hash=digest(entry)
        if key in s['request_responses']:
            saved=s['request_responses'][key]
            if saved['hash']!=hash:raise Conflict('Input ID reused with different data')
            return saved['response']
        if s['phase'] not in ('supported_practice','independent_application'):raise Conflict('当前不能提交对话')
        if entry['session_id']!=id or entry['task_id']!=s['task']['task_id']:raise Conflict('Input task mismatch')
        if entry.get('expected_session_version') is not None and entry['expected_session_version']!=row['version']:raise Conflict('Session changed')
        if len(s['turns'])>=60:raise Conflict('达到本次对话上限，请结束任务')
        support=[];kind=entry['type'];task=s['task']
        if kind=='request_hint':
            if s['phase']!='supported_practice':raise Conflict('独立任务不提供答案提示')
            lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
            target=self.curriculum.target(lesson['target_ids'][0],lesson['map_version'])
            hint=await self.provider.hint(task,s['turns'],lesson['learning_materials'],target)
            text=hint.get('text','');support=['完整示例' if self.provider.fixture else '模型提示']
            if not isinstance(text,str) or not text.strip() or len(text)>1000:raise ReviewRequired('没有可用提示')
        elif kind=='request_repeat':
            text=next((t['text'] for t in reversed(s['turns']) if t['speaker']=='partner'),task['opening']);support=['请求重复']
        else:
            turn={'turn_id':uid(),'speaker':'learner','input_id':key,'recorded_at':entry['recorded_at']}
            if kind=='speech':
                asset=self.store.get('AudioAsset',entry['audio_ref'].rsplit('/',1)[-1],owner)['payload']
                if asset['purpose']!='learner_recording':raise ValueError('Audio is not a learner recording')
                transcript=await self.provider.transcribe((self.settings.media_dir/asset['filename']).read_bytes(),asset['filename'])
                turn.update(audio_ref=entry['audio_ref'],transcript=transcript['text'],asr=transcript)
            else:
                if not entry.get('text','').strip():raise ValueError('Empty learner text')
                turn.update(transcript=entry['text'],modality='text')
            s['turns'].append(turn)
            lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
            target=self.curriculum.target(lesson['target_ids'][0],lesson['map_version'])
            reply=await self.provider.dialogue(task,s['turns'],target,s['phase'])
            text=reply.get('text','')
            if not isinstance(text,str) or not text.strip() or len(text)>1000:raise ReviewRequired('无合格对话回复')
            # Runtime role outputs get a separate semantic gate before delivery.
            review=await self.provider.review_dialogue(task,s['turns'],text,s['phase']) if hasattr(self.provider,'review_dialogue') else {'decision':'pass'}
            if review.get('decision')!='pass':
                reply=await self.provider.dialogue(task,s['turns'],target,s['phase'],feedback={'previous_reply':text,'issues':review.get('reasons',[])})
                text=reply.get('text','')
                if not isinstance(text,str) or not text.strip() or len(text)>1000:raise ReviewRequired('无合格对话回复')
                review=await self.provider.review_dialogue(task,s['turns'],text,s['phase'])
                if review.get('decision')!='pass':raise ReviewRequired('对话回复违反角色约束，请重试')
        if support:s['support_used']=sorted(set(s['support_used']+support))
        asset=await self.generator.audio(text,owner,'partner_response')
        response=DialogueResponse(session_id=id,task_id=task['task_id'],turn_id=uid(),reply_to=key,
            text=text,audio_ref=asset['audio_ref'],support_provided=support).model_dump()
        s['turns'].append({'turn_id':response['turn_id'],'speaker':'partner','text':text,'audio_ref':response['audio_ref'],'support_provided':support})
        s['request_responses'][key]={'hash':hash,'response':response}
        self.store.put('Session',id,owner,s,expected=row['version'])
        return response

    async def finish_attempt(self,id,owner):
        row=self.store.get('Session',id,owner);s=row['payload']
        task=s['task'];attempt_id=id+'/'+task['task_id']
        try:attempt=self.store.get('TaskAttempt',attempt_id,owner)['payload']
        except Missing:
            lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
            attempt=TaskAttempt(attempt_id=attempt_id,user_id=owner,session_id=id,lesson_id=s['lesson_id'],lesson_version=s['lesson_version'],
                map_version=lesson['map_version'],task_id=task['task_id'],task_version=task['task_version'],
                target_ids=lesson['target_ids'],phase=s['phase'],task_snapshot_ref=attempt_id+'/snapshot',
                turns=s['turns'],support_used=s['support_used'],fixture=s['fixture'],started_at=s['started_at'],finished_at=timestamp()).model_dump()
            if s['phase'] not in ('supported_practice','independent_application'):raise Conflict('当前没有可结束的任务')
            with self.store.transaction() as c:
                self.store.put('TaskAttempt',attempt_id,owner,attempt,conn=c)
                self.store.put('TaskSnapshot',attempt_id+'/snapshot',owner,task,conn=c)
                # Freeze the phase while evaluation is pending; inputs cannot modify recorded evidence.
                updated=copy.deepcopy(s);updated['phase']='evaluating';updated['evaluating_phase']=s['phase']
                self.store.put('Session',id,owner,updated,expected=row['version'],conn=c)
        return await self.assessor.assess(attempt,task)

    async def finish(self,id,owner):
        row=self.store.get('Session',id,owner)
        if row['payload']['phase']=='finished':
            return self.store.get('AssessmentResult',id+'/'+row['payload']['task']['task_id'],owner)['payload']
        if row['payload']['phase'] not in ('independent_application','evaluating'):raise Conflict('请完成学习和练习后再结束独立任务')
        result=await self.finish_attempt(id,owner)
        row=self.store.get('Session',id,owner);s=copy.deepcopy(row['payload']);s['phase']='finished'
        self.store.put('Session',id,owner,s,expected=row['version'])
        return result
