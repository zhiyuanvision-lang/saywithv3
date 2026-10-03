"""Session-bound try-first lexical tasks, server-tracked hints and replay-safe evidence."""
import copy
import hashlib
from pydantic import ValidationError
from sqlalchemy import update
from .byte_speech import wav_info
from .contracts import LexicalPracticeInput, LexicalPracticeAttempt
from .lexical import validate_checks, apply_checks, POLICY_VERSION
from .store import Missing, Conflict, digest

class LexicalPracticeService:
    def __init__(self,sessions):
        self.sessions=sessions;self.store=sessions.store;self.settings=sessions.settings;self.provider=sessions.provider

    def view(self,s,lesson):
        progress=s.get('lexical_progress',{})
        return [{'practice_id':p['practice_id'],'prompt_zh':p['prompt_zh'],
                 'completed':progress.get(p['practice_id'],{}).get('completed',False),
                 'support_used':progress.get(p['practice_id'],{}).get('support_used',[])} for p in lesson.get('lexical_practices',[])]

    async def input(self,id,owner,request):
        entry=LexicalPracticeInput.model_validate(request).model_dump();key=id+':'+entry['input_id'];request_hash=digest(entry)
        try:
            saved=self.store.get('LexicalPracticeAttempt',key,owner)['payload']
            if saved['request_hash']!=request_hash:raise Conflict('请求ID已被使用')
            return {**saved['response'],'session':self.sessions.view(id,owner)}
        except Missing:pass
        row=self.store.get('Session',id,owner);s=copy.deepcopy(row['payload'])
        if s['phase']!='learning':raise Conflict('当前不是生词学习阶段')
        lesson=self.store.get('LessonPackage',s['lesson_id'],owner)['payload']
        practice=next((p for p in lesson.get('lexical_practices',[]) if p['practice_id']==entry['practice_id']),None)
        if practice is None:raise Missing('LexicalPractice')
        assignment=self.store.get('TeachingAssignment',lesson['assignment_id'],owner)['payload']
        resource=next((r for r in assignment['resource_plan'].get('notebook_words',[]) if r['resource_id']==practice['resource_id']),None)
        if resource is None:raise Conflict('练习资源不匹配')
        progress=s.setdefault('lexical_progress',{}).setdefault(practice['practice_id'],{'completed':False,'support_used':[]})
        if progress['completed'] and entry['type']=='request_hint':raise Conflict('此练习已完成')
        response={'practice_id':practice['practice_id'],'message':'','hint':'','example':'','transcript':'','lexical_results':[],'completed':False}
        turns=[];valid=False;asr=None;kind=entry['type']
        if kind=='request_hint':
            level=entry['hint_level'];supports=progress['support_used']
            if level not in supports:supports.append(level)
            # Scaffolding advances by one level; an example includes its prerequisites.
            for prerequisite in {'meaning':[],'pattern':['meaning'],'example':['meaning','pattern']}[level]:
                if prerequisite not in supports:supports.append(prerequisite)
            response.update(hint=practice['explanation_zh'] if level=='meaning' else practice['hint_pattern'] if level=='pattern' else practice['example'],
                            example=practice['example'] if level=='example' else '',message='看提示后，再换成自己的内容试说。')
        elif kind=='skip':
            progress['completed']=True;response.update(completed=True,message='保留待练习记录，继续本次课程。')
        else:
            if kind=='text':
                if self.settings.mode!='fixture':raise ValueError('口语练习请提交录音')
                transcript=(entry.get('text') or '').strip()
                if not transcript:raise ValueError('请输入练习内容')
            else:
                if not entry.get('audio_ref'):raise ValueError('请提交录音')
                asset=self.store.get('AudioAsset',entry['audio_ref'].rsplit('/',1)[-1],owner)['payload']
                if asset['purpose']!='learner_recording':raise ValueError('需要学习者录音')
                file=self.settings.media_dir/asset['filename'];data=file.read_bytes()
                if hashlib.sha256(data).hexdigest()!=asset['sha256']:raise ValueError('录音校验失败')
                info,_=wav_info(data)
                if (info['rate'],info['channels'],info['width'])!=(16000,1,2):raise ValueError('录音格式不符合要求')
                asr=await self.provider.transcribe(data,asset['filename']);transcript=asr['text']
                valid=not s['fixture'] and not asset.get('fixture') and asr.get('quality')=='final_transcript_available'
            turn={'turn_id':key,'speaker':'learner','transcript':transcript,'audio_ref':entry.get('audio_ref'),'asr':asr}
            turns=[turn];checks=[]
            if valid:
                try:checks=validate_checks(await self.provider.evaluate_lexical([resource],turns,{'prompt_zh':practice['prompt_zh'],'support_used':progress['support_used']}),[resource],turns)
                except (ValidationError,ValueError,KeyError,TypeError):checks=[]
            supported=bool(progress['support_used'])
            good=any(c.get('validation')=='accepted' and c.get('result')=='correct_usage' for c in checks)
            wrong=any(c.get('validation')=='accepted' and c.get('result')=='meaning_mismatch' for c in checks)
            progress['completed']=good or any(c.get('validation')=='accepted' and c.get('result')=='not_used' for c in checks) or s['fixture']
            response.update(transcript=transcript,lexical_results=checks,completed=progress['completed'],message=
                '测试练习已收到，不计入能力。' if s['fixture'] else
                '已在语境中使用。之后会换内容再检查。' if good else
                '这个词的意思与语境不一致，可先看词义和示例再试。' if wrong else
                '已记录这次尝试。正确改述不会记为用词失败；可继续课程或看提示再练。')
        response['support_used']=progress['support_used']
        with self.store.transaction() as c:
            c.execute(update(self.store.users).where(self.store.users.c.id==owner).values(created_at=self.store.users.c.created_at))
            # CAS prevents accepting a probe against a concurrently changed/closed session.
            self.store.put('Session',id,owner,s,expected=row['version'],conn=c)
            if kind in ('speech','text') and valid:
                profile_row=self.store.get('LearnerProfile',owner,owner,c);p=copy.deepcopy(profile_row['payload'])
                apply_checks(p,response['lexical_results'],[resource],key,id,not bool(progress['support_used']),progress['support_used'],lesson['practice_task']['scenario_signature'],key,retention_days=self.settings.retention_days)
                p['profile_version']+=1;self.store.put('LearnerProfile',owner,owner,p,expected=profile_row['version'],conn=c)
            self.store.put('LexicalPracticeAttempt',key,owner,LexicalPracticeAttempt.model_validate({'schema_version':'1.0','request_hash':request_hash,'response':response,'input':entry,'turns':turns,
                'resource':resource,'practice_snapshot':practice,'lesson_id':lesson['lesson_id'],'lesson_version':lesson['lesson_version'],'map_version':lesson['map_version'],
                'model_version':self.provider.model,'policy_version':POLICY_VERSION,'fixture':s['fixture'],'evidence_valid':valid}).model_dump(),conn=c)
            self.store.emit('lexical:'+key,{'owner':owner,'attempt_ref':key},c)
        return {**response,'session':self.sessions.view(id,owner)}
