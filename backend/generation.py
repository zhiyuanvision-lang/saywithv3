"""Durable staged generation, QA gates, audio caching and immutable publication."""
import asyncio
import copy
import hashlib
import json
import logging
import re
import time
from sqlalchemy.exc import IntegrityError
from difflib import SequenceMatcher
from pathlib import Path
from pydantic import ValidationError
from .contracts import LessonPackage
from .providers import ProviderFailure, ReviewRequired, normalized, audio_normalized
from .byte_speech import wav_info
from .store import uid, digest, Conflict

log=logging.getLogger('saywith.generation')

def inspect_lesson(lesson,assignment,target):
    LessonPackage.model_validate(lesson)
    from .lesson_policy import policy_issues
    issues=policy_issues(lesson,assignment.get('resource_plan',{}).get('speaking_plan'))
    if lesson['target_ids']!=assignment['target_ids'] or lesson['map_version']!=target['map_version']:issues.append('目标或地图版本不匹配')
    if not lesson.get('practice_task'):issues.append('缺少有提示练习')
    for name in ['practice_task','independent_task']:
        task=lesson.get(name)
        if not task:continue
        contract=task['assessment_contract']
        for key in ['critical_checks','critical_meanings','acceptable_outcomes','anchors','accept_correct_paraphrase']:
            if not contract.get(key):issues.append(name+' 缺少 '+key)
        if set(contract.get('anchors',{}))!={'pass','partial','fail','unjudgeable'}:issues.append('评分锚点不完整')
        if not task.get('learner_prompt') or not task.get('opening') or not task.get('scenario_signature'):issues.append('缺少任务说明或条件签名')
        if not task['learner_facts'] or not task['partner_private_facts']:issues.append('缺少具体双方事实')
        own=set(task['learner_facts'].get('available_times',[]));partner=set(task['partner_private_facts'].get('available_times',[]))
        if own or partner:
            possible=own&partner
            if not possible or set(contract.get('acceptable_times',[]))!=possible:
                issues.append(name+'.assessment_contract.acceptable_times 必须为双方 available_times 的完整交集 '+json.dumps(sorted(possible),ensure_ascii=False)+'；该字段实际为 '+json.dumps(contract.get('acceptable_times'),ensure_ascii=False)+'。把该数组写入 assessment_contract，不是仅写入 partner_private_facts。若交集为空则修改双方时间条件，使任务可解。')
    previous=assignment.get('resource_plan',{}).get('previous_task')
    if previous and previous['learner_facts']==lesson['independent_task']['learner_facts'] and previous['partner_private_facts']==lesson['independent_task']['partner_private_facts']:issues.append('复习任务与基准任务事实相同，请更换事实')
    practice=lesson.get('practice_task',{})
    independent=lesson['independent_task']
    if practice and (practice['learner_facts']==independent['learner_facts'] and practice['partner_private_facts']==independent['partner_private_facts']):issues.append('独立变体未改变任务条件')
    if any(x in independent['allowed_support'] for x in ('完整答案','关键词提示','句型补全')):issues.append('独立检查提供了答案提示')
    if len(lesson['learning_materials'])>assignment['difficulty']['new_expression_limit']:issues.append('新表达超过本次负荷限制')
    for material in lesson['learning_materials']:
        if re.search(r'\+|_{2,}|<[^>]+>|\[[^\]]+\]',material['expression']):
            issues.append('learning_materials.expression 必须为可直接朗读的完整示例，例如 How about four thirty?；句型占位符只能放入 hint_pattern，不能合成语音。')
        if not material['expression'].strip() or not material.get('explanation_zh') or not material.get('personal_prompt_zh'):issues.append('学习材料缺少解释或个人替换要求')
    selected={r['resource_id']:r for r in assignment.get('resource_plan',{}).get('notebook_words',[])}
    practices=lesson.get('lexical_practices',[])
    if len(practices)!=len(selected) or {p['resource_id'] for p in practices}!=set(selected):issues.append('收藏词练习必须与本次选词一一对应')
    for p in practices:
        r=selected.get(p['resource_id'])
        if not r or p['sense_id']!=r['sense_id']:issues.append('生词练习词义关联不匹配');continue
        if not all(p.get(k,'').strip() for k in ('prompt_zh','example','explanation_zh','hint_pattern')):issues.append('生词练习缺少意图、例句、解释或提示')
        if not set(re.findall(r"[a-z]+(?:['’-][a-z]+)*",p['example'].lower()))&set(r['forms']):issues.append('生词示例未使用所选词或词形')
        if set(re.findall(r"[a-z]+(?:['’-][a-z]+)*",p['prompt_zh'].lower()))&set(r['forms']):issues.append('先尝试的意图泄露了英文目标词。prompt_zh只写具体中文交流意图，例如“询问Alex明天下午是否有空”。删除英文词、句式及“用该词说”的要求；保留本任务的具体事实。')
    return issues

class Generator:
    def __init__(self,store,planner,curriculum,provider,settings):
        self.store=store;self.planner=planner;self.curriculum=curriculum;self.provider=provider;self.settings=settings

    def defer_notebook(self,row,p,reasons):
        selected=p['assignment'].get('resource_plan',{}).get('notebook_words',[])
        text=json.dumps(reasons,ensure_ascii=False).lower()
        if not selected or p.get('notebook_deferred') or not any(term in text for term in ('生词','收藏词','目标词','词义','lexical','notebook')):return False
        # A failed optional vocabulary candidate must not replace or block the main goal.
        report=p.get('text_report') or {'report_id':uid(),'stage':'text','decision':'fail','issues':reasons}
        original=p['assignment']['assignment_id'];assignment=copy.deepcopy(p['assignment']);assignment['assignment_id']=uid()
        assignment['resource_plan'].update(notebook_words=[],notebook_deferred=[{'resource_id':r['resource_id'],'reason':'本次词汇内容未通过质检，保留待练习'} for r in selected],deferred_from_assignment_id=original,notebook_deferral_report_ref=report['report_id'])
        p['assignment']=assignment;p['notebook_deferred']=True;p['text_revisions']=0
        p['repair_feedback']={'issues':['本次先推进原沟通目标，收藏词延后。lexical_practices必须为空数组，保留目标、难度与用户语境。']}
        p.pop('lesson',None);p.pop('text_report',None)
        with self.store.transaction() as c:
            self.store.advance(row,'generating_text',p,c,release=True)
            self.store.put('TeachingAssignment',assignment['assignment_id'],row['owner'],assignment,conn=c)
            self.store.put('QualityReport',report['report_id'],row['owner'],report,conn=c)
        return True

    def audio_key(self,text,version="clock-v3"):
        return digest({'text':text,'speaker':self.settings.doubao_speaker,'resource':self.settings.doubao_tts_resource,
                       'fixture':self.provider.fixture,'speech_text_version':version})

    async def concurrent(self,items,operation):
        """Bound provider load; persist each result on the worker, cancel siblings on failure."""
        semaphore=asyncio.Semaphore(3)
        async def run(item):
            async with semaphore:return item,await operation(item)
        tasks=[asyncio.create_task(run(item)) for item in items]
        try:
            for future in asyncio.as_completed(tasks):yield await future
        finally:
            for task in tasks:
                if not task.done():task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)

    async def check_audio(self,asset):
        data=(self.settings.media_dir/asset['filename']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=asset['sha256']:raise ReviewRequired('音频文件校验失败，需要重新准备')
        transcription=await self.provider.transcribe(data,asset['filename'])
        actual=audio_normalized(transcription['text']);expected=audio_normalized(asset['text'])
        alignment=SequenceMatcher(None,expected,actual).ratio()
        if alignment<0.85:raise ReviewRequired('合成音频与文本对照不一致，需要音频审核')
        numbers=lambda x:re.findall(r'\b\d+\b',x)
        negation=r"\b(not|can t|don t|isn t|won t|couldn t|didn t|doesn t)\b"
        if numbers(actual)!=numbers(expected) or bool(re.search(negation,actual))!=bool(re.search(negation,expected)):
            raise ReviewRequired('关键数字或否定信息需要音频审核')
        return {'asset_id':asset['asset_id'],'expected':asset['text'],'transcript':transcription['text'],
                'similarity':alignment,'decision':'pass','asr':transcription}

    def remember_audio_check(self,asset,owner):
        # A cache hit skips ASR only for the exact previously verified bytes/text/voice.
        from .store import Missing
        with self.store.transaction() as c:
            owned=self.store.get('AudioAsset',asset['asset_id'],owner,conn=c)
            self.store.put('AudioAsset',asset['asset_id'],owner,{**owned['payload'],'quality':'passed'},expected=owned['version'],conn=c)
            key=self.audio_key(asset['text'])
            try:cached=self.store.get('AudioCache',key,conn=c)
            except Missing:return
            if cached['payload']['sha256']==asset['sha256']:
                self.store.put('AudioCache',key,'system',{**cached['payload'],'quality':'passed'},expected=cached['version'],conn=c)

    async def audio(self,text,owner,purpose):
        key=self.audio_key(text)
        from .store import Missing
        for cache_key in (key,self.audio_key(text,version='clock-v2')):
            try:
                row=self.store.get('AudioCache',cache_key)
                asset=row['payload']
                # Previously verified v2 speech remains safe to reuse. Unchecked old
                # abbreviations must be synthesized with the clearer pronunciation.
                if cache_key!=key and asset.get('quality')!='passed':continue
                file=self.settings.media_dir/asset['filename']
                if not file.is_file():continue
                if hashlib.sha256(file.read_bytes()).hexdigest()!=asset['sha256']:raise ReviewRequired('缓存音频文件校验失败，需要重新准备')
                if cache_key!=key:
                    with self.store.transaction() as c:
                        try:
                            with c.begin_nested():self.store.put('AudioCache',key,'system',asset,conn=c)
                        except IntegrityError:pass
                try:self.store.get('AudioAsset',asset['asset_id'],owner);return asset
                except Missing:
                    id=uid();cloned={**asset,'asset_id':id,'audio_ref':'/v1/media/'+id}
                    self.store.put('AudioAsset',id,owner,cloned)
                    return cloned
            except Missing:pass
        data=await self.provider.speech(text)
        info,_=wav_info(data)
        if info['channels']!=1 or info['width']!=2:raise ReviewRequired('Invalid generated speech format')
        id=uid();file=self.settings.media_dir/(id+'.wav');file.write_bytes(data)
        asset={'asset_id':id,'audio_ref':'/v1/media/'+id,'filename':file.name,'text':text,'purpose':purpose,
            'fixture':self.provider.fixture,'sha256':hashlib.sha256(data).hexdigest(),'info':info,
            'quality':'fixture' if self.provider.fixture else 'pending','voice_version':self.settings.doubao_tts_resource}
        self.store.put('AudioAsset',id,owner,asset)
        # Cache keys are global but API access remains scoped to owner/lesson.
        with self.store.transaction() as c:
            try:
                with c.begin_nested():self.store.put('AudioCache',key,'system',asset,conn=c)
            except IntegrityError:
                log.info('Audio cache already present')
        return asset

    async def run_one(self,worker):
        row=self.store.claim(worker)
        if row is None:return False
        p=copy.deepcopy(row['payload']);owner=row['owner']
        try:
            if 'assignment' not in p:
                profile=self.store.get('LearnerProfile',owner,owner)['payload']
                expected=p['request'].get('profile_version')
                if expected is not None and expected!=profile['profile_version']:raise ReviewRequired('能力记录已经更新，请重新规划')
                row=self.store.advance(row,'planning',p)
                assignment,target=self.planner.plan(profile,p['request'])
                p.update(assignment=assignment,target=target)
                row=self.store.advance(row,'generating_text',p)
            if 'lesson' not in p:
                generated=await self.provider.generate(p['assignment'],p['target'],p.get('repair_feedback'))
                generated.update(schema_version='1.0',lesson_id=uid(),lesson_version=1,
                    assignment_id=p['assignment']['assignment_id'],map_version=p['target']['map_version'],
                    target_ids=p['assignment']['target_ids'],quality={'status':'draft'},learner_ready=False,
                    provenance={'model_version':self.provider.model,'prompt_version':'lesson-lexical-v2',
                        'map_version':p['target']['map_version'],'rules_version':'qa-v1','fixture':self.provider.fixture})
                for name in ['practice_task','independent_task']:
                    if generated.get(name):generated[name].update(task_id=uid(),task_version=1)
                for p0 in generated.get('lexical_practices',[]):p0['practice_id']=uid()
                for m in generated.get('learning_materials',[]):m['audio_ref']=None
                for m in generated.get('learning_materials',[]):
                    # Resource IDs are assigned on the server, not trusted model claims.
                    m['resource_id']='expr:'+digest({'expression':normalized(m['expression']),'target':p['target']['target_id']})[:24]
                generated['practice_task_ref']='tasks/'+generated.get('practice_task',{}).get('task_id','missing')
                try:
                    lesson=LessonPackage.model_validate(generated).model_dump()
                except ValidationError as error:
                    if p.get('text_revisions',0)<2 and not self.provider.fixture:
                        p['text_revisions']=p.get('text_revisions',0)+1
                        p['repair_feedback']='修复JSON结构，禁止额外字段（例如根对象type）；只返回LessonPackage。'+str(error)[:3000]
                        self.store.advance(row,'generating_text',p,release=True)
                        return True
                    if self.defer_notebook(row,p,str(error)):return True
                    raise ReviewRequired('课程结构校验未通过：'+str(error)[:1200])
                p['lesson']=lesson;row=self.store.advance(row,'checking_text',p)
            if 'text_report' not in p:
                issues=inspect_lesson(p['lesson'],p['assignment'],p['target'])
                review=await self.provider.review(p['lesson'],{**p['target'],'lexical_resources':p['assignment']['resource_plan'].get('notebook_words',[]),'speaking_plan':p['assignment']['resource_plan'].get('speaking_plan')}) if not issues else {'decision':'fail','reasons':issues}
                p['text_report']={'report_id':uid(),'stage':'text','checker_version':'qa-v1','decision':review.get('decision'),
                                  'issues':issues,'semantic_review':review,'independent_model':False}
                if issues or review.get('decision')!='pass':
                    if p.get('text_revisions',0)<2 and not self.provider.fixture:
                        p['text_revisions']=p.get('text_revisions',0)+1
                        p['repair_feedback']={'previous_lesson':p['lesson'],'issues':review.get('reasons',issues)}
                        p.pop('lesson');p.pop('text_report')
                        self.store.advance(row,'generating_text',p,release=True)
                        return True
                    if self.defer_notebook(row,p,review.get('reasons',issues)):return True
                    raise ReviewRequired('课程质检未通过：'+json.dumps(review.get('reasons',issues),ensure_ascii=False))
                row=self.store.advance(row,'generating_audio',p)
            lesson=p['lesson']
            if 'audio_assets' not in p:p['audio_assets']=[]
            pending=[]
            # Dialogue demonstration also needs validated partner audio, not consecutive learner lines.
            for m in lesson['learning_materials'][1:]:
                if m.get('partner_line') and not any(a.get('text')==m['partner_line'] for a in p['audio_assets']):
                    p['audio_assets'].append(await self.audio(m['partner_line'],owner,'partner_opening'))
                    row=self.store.advance(row,'generating_audio',p)
            for index,m in enumerate(lesson['learning_materials']):
                if not m['audio_ref']:pending.append(('material',index,m['expression']))
            for name in ['practice_task','independent_task']:
                task=lesson[name]
                if not any(a.get('task_id')==task['task_id'] for a in p['audio_assets']):pending.append(('task',name,task['opening']))
            async def synthesize(item):return await self.audio(item[2],owner,'learning_example' if item[0]=='material' else 'partner_opening')
            async for item,asset in self.concurrent(pending,synthesize):
                if item[0]=='material':lesson['learning_materials'][item[1]]['audio_ref']=asset['audio_ref']
                else:asset={**asset,'task_id':lesson[item[1]]['task_id']}
                p['audio_assets'].append(asset)
                row=self.store.advance(row,'generating_audio',p)
            row=self.store.advance(row,'checking_audio',p)
            reports=[]
            unchecked=[a for a in p['audio_assets'] if a['quality']!='passed' and not self.provider.fixture]
            async for asset,check in self.concurrent(unchecked,self.check_audio):
                self.remember_audio_check(asset,owner)
                asset['quality']='passed'
                p.setdefault('audio_alignment_checks',[]).append(check)
                reports.append(check)
                row=self.store.advance(row,'checking_audio',p)
            p['audio_report']={'report_id':uid(),'stage':'audio','decision':'fixture' if self.provider.fixture else 'pass','checks':reports}
            lesson['quality']={'status':'draft' if self.provider.fixture else 'approved','report_ref':p['text_report']['report_id'],'qa_version':'qa-v1'}
            lesson['learner_ready']=not self.provider.fixture
            LessonPackage.model_validate(lesson)
            with self.store.transaction() as c:
                # CAS gates all writes, so cancellation/expired workers cannot publish.
                row=self.store.advance(row,'preview_ready' if self.provider.fixture else 'approved',p,c,release=True)
                self.store.put('LessonPackage',lesson['lesson_id'],owner,lesson,conn=c)
                self.store.put('QualityReport',p['text_report']['report_id'],owner,p['text_report'],conn=c)
                self.store.put('QualityReport',p['audio_report']['report_id'],owner,p['audio_report'],conn=c)
                self.store.emit('lesson:'+lesson['lesson_id']+':1',{'lesson_id':lesson['lesson_id'],'owner':owner,'learner_ready':lesson['learner_ready']},c)
            log.info('generation completed job=%s mode=%s',row['id'],self.settings.mode)
        except Conflict:
            log.info('generation lease lost job=%s',row['id'])
        except (ReviewRequired,ValidationError,ValueError) as e:
            p['error']={'code':'needs_review','message':str(e)[:1200]}
            try:self.store.advance(row,'needs_review',p,release=True)
            except Conflict:pass
        except Exception as e:
            log.warning('generation failed job=%s error_type=%s',row['id'],type(e).__name__)
            p['error']={'code':'provider_or_runtime_error','message':type(e).__name__}
            state='failed' if row['attempts']>=self.settings.max_job_attempts else row['state']
            try:self.store.advance(row,state,p,release=True,delay=min(30,2**row['attempts']))
            except Conflict:pass
        return True
