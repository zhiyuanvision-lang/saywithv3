"""Evaluate real attempts, validate evidence, update conditional learner states."""
import copy
import time
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from .contracts import AssessmentResult, AssessmentCandidate
from pydantic import ValidationError
from .byte_speech import wav_info
from .store import uid, Missing, Conflict
from .lexical import validate_checks, apply_checks

def timestamp():return datetime.now(timezone.utc).isoformat()

class Assessor:
    def __init__(self,store,curriculum,provider,settings):
        self.store=store;self.curriculum=curriculum;self.provider=provider;self.settings=settings

    async def assess(self,attempt,task,candidate=None):
        owner=attempt['user_id'];id=attempt['attempt_id']
        try:return self.store.get('AssessmentResult',id,owner)['payload']
        except Missing:pass
        target=self.curriculum.target(attempt['target_ids'][0],attempt['map_version'])
        turns=attempt['turns'];learner=[t for t in turns if t['speaker']=='learner']
        spoken=task['modality']=='spoken_interaction'
        problems=[]
        if attempt.get('status')=='abandoned':problems.append('任务已退出，不作能力失败判定')
        if attempt.get('fixture'):problems.append('测试用例不作为用户能力证据')
        if not learner:problems.append('没有学习者表现')
        if spoken and any(not t.get('audio_ref') or t.get('asr',{}).get('quality')!='final_transcript_available' for t in learner):
            problems.append('缺少本目标所需的音频和最终识别证据')
        for turn in learner:
            if not turn.get('audio_ref'):continue
            try:
                asset=self.store.get('AudioAsset',turn['audio_ref'].rsplit('/',1)[-1],owner)['payload']
                file=self.settings.media_dir/asset['filename']
                if asset['purpose']!='learner_recording' or asset.get('fixture') or not file.is_file():
                    problems.append('录音来源或资产不可用')
                elif __import__('hashlib').sha256(file.read_bytes()).hexdigest()!=asset['sha256']:
                    problems.append('录音资产校验不一致')
                else:
                    info,_=wav_info(file.read_bytes())
                    if (info['rate'],info['channels'],info['width'])!=(16000,1,2):problems.append('录音格式不符合证据要求')
            except ValueError:problems.append('录音格式损坏')
            except Missing:problems.append('录音证据不存在或不属于用户')
        if len(learner)>30:problems.append('超出评价输入限制')
        candidate=(candidate if candidate is not None else await self.provider.evaluate(task,turns,target)) if not problems else {
            'result':'unjudgeable','confidence':'low','checks':[],'diagnosis':[]}
        try:candidate=AssessmentCandidate.model_validate(candidate).model_dump()
        except ValidationError:
            problems.append('模型评价结构不合法')
            candidate={'result':'unjudgeable','confidence':'low','checks':[],'diagnosis':[]}
        refs={t['turn_id'] for t in turns}
        checks=candidate.get('checks',[])
        needed=task['assessment_contract']['critical_checks']
        if candidate.get('result') not in ('completed','partial','failed','unjudgeable'):problems.append('非法评价结果')
        if candidate.get('confidence') not in ('high','medium','low'):problems.append('评价缺少可信度')
        if len(checks)!=len(needed) or {c.get('criterion') for c in checks}!=set(needed):problems.append('关键检查未全部评价')
        for check in checks:
            if check.get('result') not in ('met','not_met','unjudgeable'):problems.append('非法检查状态')
            if not check.get('evidence_refs') or not set(check.get('evidence_refs',[]))<=refs:problems.append('证据引用不存在')
            if check.get('result')=='met' and not any(t['speaker']=='learner' and t['turn_id'] in check.get('evidence_refs',[]) for t in turns):
                problems.append('完成判定缺少学习者证据')
        if candidate.get('result')=='completed' and not all(c.get('result')=='met' for c in checks):problems.append('完成与检查结果矛盾')
        if candidate.get('confidence')=='low':problems.append('低可信度需要更多证据')
        # Unknown diagnoses stay hypotheses; never store them as established causes.
        diagnoses=[{**d,'status':'hypothesis'} for d in candidate.get('diagnosis',[]) if isinstance(d,dict)]
        lexical=[]
        resources=attempt.get('lexical_resources',[])
        if not problems and resources:
            try:
                lexical=validate_checks(await self.provider.evaluate_lexical(resources,turns,{'task':task,'support_used':attempt['support_used']}),resources,turns)
            except (ValidationError,ValueError,TypeError,KeyError):lexical=[]
            except Exception:
                # Lexical analysis is supplementary and must not block task evidence.
                lexical=[]
        result=AssessmentResult(assessment_id=uid(),attempt_id=id,assessment_version='eval-v1',model_version=self.provider.model,
            target_results=[{'target_id':target['target_id'],'result':'unjudgeable' if problems else candidate['result'],
                'checks':checks,'confidence':candidate.get('confidence','low'),'diagnosis':diagnoses,
                'fluency':'not_calibrated','pronunciation':'not_assessed'}],
            lexical_results=lexical,evidence_ids=[] if problems else [uid()],validation={'status':'rejected' if problems else 'accepted',
                'checks':problems or ['证据引用存在','任务条件和实际支持已保存','音频模态证据可用' if spoken else '文字任务证据可用'],
                'validation_version':'validation-v1'}).model_dump()
        for retry in range(3):
            try:
                with self.store.transaction() as c:
                    try:return self.store.get('AssessmentResult',id,owner,c)['payload']
                    except Missing:pass
                    self.store.put('AssessmentResult',id,owner,result,conn=c)
                    if result['validation']['status']=='accepted':self.update_profile(attempt,task,result,c)
                    self.store.emit('assessment:'+id,{'assessment_id':result['assessment_id'],'owner':owner},c)
                return result
            except (Conflict,IntegrityError):
                if retry==2:raise

    def update_profile(self,attempt,task,result,conn):
        owner=attempt['user_id'];row=self.store.get('LearnerProfile',owner,owner,conn)
        profile=copy.deepcopy(row['payload']);id=attempt['target_ids'][0]
        states={s['target_id']:s for s in profile['target_states']}
        state=states.setdefault(id,{'target_id':id,'independent':'insufficient_evidence','retention':'not_checked',
            'transfer':'not_checked','support_dependency':[],'evidence_ids':[],'observations':[]})
        r=result['target_results'][0];now=time.time()
        supports=attempt['support_used'];independent=attempt['phase']=='independent_application' and not any(x in ('意图提示','句型提示','完整示例','所学表达','模型提示','查词释义','回答示范') for x in supports)
        evidence={'evidence_id':result['evidence_ids'][0],'attempt_id':attempt['attempt_id'],'session_id':attempt['session_id'],
            'time':now,'completed':r['result']=='completed','independent':independent,
            'review_metadata':attempt.get('review_metadata',{}),'scenario_signature':task['scenario_signature'],'confidence':r['confidence'],'support_used':supports}
        state['observations'].append(evidence);state['evidence_ids'].append(evidence['evidence_id'])
        state['support_dependency']=sorted(set(state['support_dependency']+supports))
        successes=[e for e in state['observations'] if e['independent'] and e['completed']]
        if r['result']=='completed':
            if not independent and state['independent'] not in ('demonstrated','provisional'):state['independent']='supported'
            elif independent:state['independent']='demonstrated' if len({e['session_id'] for e in successes})>=2 else 'provisional'
            if independent and attempt.get('review_metadata',{}).get('purpose')=='transfer' and attempt.get('review_metadata',{}).get('transfer_validated') and len({e['scenario_signature'] for e in successes})>=2:state['transfer']='demonstrated'
            previous=[e for e in successes if e['attempt_id']!=attempt['attempt_id']]
            if independent and attempt.get('review_metadata',{}).get('retention_eligible',True) and previous and now-max(e['time'] for e in previous)>=self.settings.retention_days*86400:state['retention']='demonstrated'
        elif independent:
            state['independent']='needs_practice'
            if successes:state['retention']='needs_recheck'
        state['confidence']='provisional_rule_requires_pilot'
        state['last_result']=r['result'];state['updated_at']=now
        state['due_at']=now+(self.settings.retention_days*86400 if independent and r['result']=='completed' else 86400)
        apply_checks(profile,result.get('lexical_results',[]),attempt.get('lexical_resources',[]),attempt['attempt_id'],attempt['session_id'],independent,supports,task['scenario_signature'],result['assessment_id'],retention_days=self.settings.retention_days)
        profile['target_states']=list(states.values());profile['profile_version']+=1
        self.store.put('LearnerProfile',owner,owner,profile,expected=row['version'],conn=conn)
        self.store.put('Evidence',evidence['evidence_id'],owner,{'assessment':result,'observation':evidence,
            'task_snapshot_ref':attempt['task_snapshot_ref'],'map_version':attempt['map_version']},conn=conn)
