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
from .providers import ProviderFailure, ReviewRequired, normalized
from .byte_speech import wav_info
from .store import uid, digest, Conflict

log=logging.getLogger('saywith.generation')

def inspect_lesson(lesson,assignment,target):
    LessonPackage.model_validate(lesson)
    issues=[]
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
            if not possible or set(contract.get('acceptable_times',[]))!=possible:issues.append('时间任务无解或可接受结果不完整')
    practice=lesson.get('practice_task',{})
    independent=lesson['independent_task']
    if practice and (practice['learner_facts']==independent['learner_facts'] and practice['partner_private_facts']==independent['partner_private_facts']):issues.append('独立变体未改变任务条件')
    if any(x in independent['allowed_support'] for x in ('完整答案','关键词提示','句型补全')):issues.append('独立检查提供了答案提示')
    if len(lesson['learning_materials'])>assignment['difficulty']['new_expression_limit']:issues.append('新表达超过本次负荷限制')
    for material in lesson['learning_materials']:
        if not material['expression'].strip() or not material.get('explanation_zh') or not material.get('personal_prompt_zh'):issues.append('学习材料缺少解释或个人替换要求')
    return issues

class Generator:
    def __init__(self,store,planner,curriculum,provider,settings):
        self.store=store;self.planner=planner;self.curriculum=curriculum;self.provider=provider;self.settings=settings

    async def audio(self,text,owner,purpose):
        key=digest({'text':text,'speaker':self.settings.doubao_speaker,'resource':self.settings.doubao_tts_resource,
                    'fixture':self.provider.fixture})
        from .store import Missing
        try:
            row=self.store.get('AudioCache',key)
            file=self.settings.media_dir/row['payload']['filename']
            if file.is_file():
                asset=row['payload']
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
                    provenance={'model_version':self.provider.model,'prompt_version':'lesson-v1',
                        'map_version':p['target']['map_version'],'rules_version':'qa-v1','fixture':self.provider.fixture})
                for name in ['practice_task','independent_task']:
                    if generated.get(name):generated[name].update(task_id=uid(),task_version=1)
                for m in generated.get('learning_materials',[]):m['audio_ref']=None
                for m in generated.get('learning_materials',[]):
                    # Resource IDs are assigned on the server, not trusted model claims.
                    m['resource_id']='expr:'+digest({'expression':normalized(m['expression']),'target':p['target']['target_id']})[:24]
                generated['practice_task_ref']='tasks/'+generated.get('practice_task',{}).get('task_id','missing')
                lesson=LessonPackage.model_validate(generated).model_dump()
                p['lesson']=lesson;row=self.store.advance(row,'checking_text',p)
            if 'text_report' not in p:
                issues=inspect_lesson(p['lesson'],p['assignment'],p['target'])
                review=await self.provider.review(p['lesson'],p['target']) if not issues else {'decision':'fail','reasons':issues}
                p['text_report']={'report_id':uid(),'stage':'text','checker_version':'qa-v1','decision':review.get('decision'),
                                  'issues':issues,'semantic_review':review,'independent_model':False}
                if issues or review.get('decision')!='pass':
                    if p.get('text_revisions',0)<2 and not self.provider.fixture:
                        p['text_revisions']=p.get('text_revisions',0)+1
                        p['repair_feedback']={'previous_lesson':p['lesson'],'issues':review.get('reasons',issues)}
                        p.pop('lesson');p.pop('text_report')
                        self.store.advance(row,'generating_text',p,release=True)
                        return True
                    raise ReviewRequired('课程质检未通过：'+json.dumps(review.get('reasons',issues),ensure_ascii=False))
                row=self.store.advance(row,'generating_audio',p)
            lesson=p['lesson']
            if 'audio_assets' not in p:p['audio_assets']=[]
            for m in lesson['learning_materials']:
                if not m['audio_ref']:
                    asset=await self.audio(m['expression'],owner,'learning_example')
                    m['audio_ref']=asset['audio_ref'];p['audio_assets'].append(asset)
                    row=self.store.advance(row,'generating_audio',p)
            for name in ['practice_task','independent_task']:
                task=lesson[name]
                if not any(a.get('task_id')==task['task_id'] for a in p['audio_assets']):
                    asset=await self.audio(task['opening'],owner,'partner_opening')
                    p['audio_assets'].append({**asset,'task_id':task['task_id']})
                    row=self.store.advance(row,'generating_audio',p)
            row=self.store.advance(row,'checking_audio',p)
            reports=[]
            for asset in p['audio_assets']:
                if asset['quality']=='passed' or self.provider.fixture:continue
                transcription=await self.provider.transcribe((self.settings.media_dir/asset['filename']).read_bytes(),asset['filename'])
                actual=normalized(transcription['text']);expected=normalized(asset['text'])
                if SequenceMatcher(None,expected,actual).ratio()<0.85:
                    raise ReviewRequired('合成音频与文本对照不一致，需要音频审核')
                # Critical numbers and negations need strict matching after number normalization.
                numbers=lambda x:re.findall(r'\b\d+\b',x)
                negation=r"\b(not|can t|don t|isn t|won t|couldn t|didn t|doesn t)\b"
                if numbers(actual)!=numbers(expected) or bool(re.search(negation,actual))!=bool(re.search(negation,expected)):
                    raise ReviewRequired('关键数字或否定信息需要音频审核')
                asset['quality']='passed';reports.append({'asset_id':asset['asset_id'],'decision':'pass','asr':transcription})
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
