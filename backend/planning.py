"""Rule-based scheduling and concrete teaching assignments."""
import re
import time
from datetime import datetime
from .contracts import TeachingAssignment
from .store import uid

STAGES=['Pre-A1','A1','A2','B1','B2','C1','C2']

class Planner:
    def __init__(self,curriculum,store,retention_days=7):self.curriculum=curriculum;self.store=store;self.retention_days=retention_days

    def contacts(self,profile):
        """Learning exposure is separate from assessed ability; fixture sessions are excluded."""
        contacts={}
        for row in self.store.list('Session',profile['user_id']):
            session=row['payload']
            if session.get('fixture') or not session.get('learning_events'):continue
            lesson=self.store.get('LessonPackage',session['lesson_id'],profile['user_id'])['payload']
            for event in session['learning_events']:
                at=datetime.fromisoformat(event['time']).timestamp()
                for target_id in lesson['target_ids']:contacts[target_id]=max(contacts.get(target_id,0),at)
        return contacts

    def recommendations(self,profile):
        states={s['target_id']:s for s in profile['target_states']};contacts=self.contacts(profile)
        learned=[];due=[]
        for target_id in sorted(states.keys()|contacts.keys()):
            try:target=self.curriculum.target(target_id)
            except KeyError:continue
            state=states.get(target_id,{})
            due_at=state.get('due_at',contacts.get(target_id,time.time())+self.retention_days*86400)
            item={'target_id':target_id,'title':target['outcome'],'minutes':5,'task_count':1,
                  'reason':'复习已学内容，先听对方，再用语音回答。','due_at':due_at,
                  'exposure_only':not bool(state)}
            learned.append(item)
            if due_at<=time.time():due.append(item)
        due.sort(key=lambda x:x['due_at'])
        target,purpose,reason=self.select_target(profile)
        upcoming={'target_id':target['target_id'],'title':target['outcome'],'minutes':10,'task_count':1,'reason':reason,'purpose':purpose}
        return {'recommended':due[0] if due else None,'due_count':len(due),'learned':learned,'next_learning':upcoming}

    def select_target(self,profile,explicit=None):
        states={x['target_id']:x for x in profile['target_states']}
        contacts=self.contacts(profile)
        stage=profile['preferences'].get('reference_stage','A2')
        if stage not in STAGES:stage='A2'
        purpose='new';reason='扩展当前难度下尚未训练的交流能力'
        if explicit:
            target=self.curriculum.target(explicit);reason='用户选择此沟通目标'
        else:
            map_version=self.curriculum.active_version
            candidates=self.curriculum.list_targets(stage=stage,map_version=map_version)
            # Move the practice band only after every goal in the current band has
            # repeated independent and transfer evidence; this is not certification.
            while candidates and all(states.get(t['target_id'],{}).get('independent')=='demonstrated'
                                     and states.get(t['target_id'],{}).get('transfer')=='demonstrated' for t in candidates):
                index=STAGES.index(stage)
                if index==len(STAGES)-1:break
                higher=self.curriculum.list_targets(stage=STAGES[index+1],map_version=map_version)
                if not higher:break
                # Overdue practice across previously completed bands remains eligible.
                if any(states.get(t['target_id'],{}).get('due_at',float('inf'))<=time.time() for t in candidates):break
                stage=STAGES[index+1];candidates=higher
            now=time.time()
            priorities=[]
            for t in candidates:
                s=states.get(t['target_id'],{})
                due=s.get('due_at',contacts.get(t['target_id'],float('inf'))+self.retention_days*86400)<=now
                family=t['target_id'].split('.')[0]
                coverage=sum(1 for x in states if x.startswith(family+'.'))
                need=0 if due else 1 if s.get('independent') in ('needs_practice','supported') else 2 if not s and t['target_id'] not in contacts else 3
                priorities.append((need,coverage,t['target_id']))
            if not priorities:raise ValueError('No targets at requested stage')
            id=min(priorities)[2];target=next(t for t in candidates if t['target_id']==id)
        state=states.get(target['target_id'],{})
        if state.get('independent') in ('needs_practice','supported'):purpose='consolidation';reason='此前表现仍需要帮助，先减少提示完成此目标'
        elif state.get('due_at',float('inf'))<=time.time():purpose='retention';reason='之前完成过此目标，现在检查隔期是否仍能完成'
        elif state.get('independent')=='demonstrated' and state.get('transfer')!='demonstrated':purpose='transfer';reason='已有独立完成证据，换条件验证是否能应用'
        elif not state and target['target_id'] in contacts:purpose='consolidation';reason='已经接触此目标，继续检查独立表达'
        elif not state:purpose='diagnostic';reason='目前没有此目标的表现证据，先检查起点'
        return target,purpose,reason

    def plan(self,profile,request):
        target,purpose,reason=self.select_target(profile,request.get('target_id'))
        state=next((s for s in profile['target_states'] if s['target_id']==target['target_id']),{})
        review=request.get('entry_kind')=='review'
        if review and not state and target['target_id'] not in self.contacts(profile):raise ValueError('此目标还没有已学表现记录')
        if review and purpose in ('new','diagnostic'):purpose='consolidation';reason='复习已经接触的目标，先尝试独立完成'
        successes=[e for e in state.get('observations',[]) if e.get('independent') and e.get('completed')]
        baseline=max(successes,key=lambda e:e['time']) if successes else None
        metadata={'target_id':target['target_id'],'purpose':purpose,'policy_version':'review-v1','entry_kind':'review' if review else 'course',
                  'baseline_attempt_id':baseline['attempt_id'] if baseline else None,
                  'baseline_time':baseline['time'] if baseline else None,'planned_at':time.time(),
                  'required_gap_days':self.retention_days,
                  'transfer_conditions':[],'transfer_validated':False}
        known=[x['resource_id'] for x in profile['resource_states'] if x.get('understanding')=='demonstrated']
        refs=target['reviewed_standard_references']
        words=re.findall(r'\b[a-zA-Z]{4,}\b',' '.join(r.get('outcome_en','') for r in refs))
        stop={'with','that','from','this','simple','their','basic','using','about','someone','people','information'}
        candidates=[]
        for word in dict.fromkeys(w.lower() for w in words if w.lower() not in stop):
            candidates.extend(self.curriculum.repository.query_senses(query=word,limit=2,excluded_ids=tuple(known)))
            if len(candidates)>=8:break
        assignment=TeachingAssignment(assignment_id=uid(),user_id=profile['user_id'],map_version=target['map_version'],
            profile_version=profile['profile_version'],target_ids=[target['target_id']],reason=reason,
            context=request.get('context') or profile['preferences'].get('context','校园与日常生活'),
            resource_plan={'review':known[:5],'focus':[target['outcome']], 'candidates':candidates,
                           'known_resources':known,'candidate_policy':'候选不是强制新词，按实际任务核查必要性'},
            difficulty={'support':'示例→渐退提示→独立应用','reference_stage':target['reference_stage'],
                        'new_expression_limit':3,'purpose':purpose},purpose=purpose,
            review_metadata=metadata,completion_standard=target['outcome'],minutes=request.get('minutes',10)).model_dump()
        if review:
            previous=[r['payload'] for r in self.store.list('TaskAttempt',profile['user_id']) if target['target_id'] in r['payload'].get('target_ids',[]) and r['payload'].get('phase')=='independent_application']
            if previous:
                latest=max(previous,key=lambda a:a.get('finished_at',''))
                from .store import Missing
                try:assignment['resource_plan']['previous_task']=self.store.get('TaskSnapshot',latest['task_snapshot_ref'],profile['user_id'])['payload']
                except Missing:pass
        if baseline and 'previous_task' not in assignment['resource_plan']:
            from .store import Missing
            try:assignment['resource_plan']['previous_task']=self.store.get('TaskSnapshot',baseline['attempt_id']+'/snapshot',profile['user_id'])['payload']
            except Missing:pass
        assignment['resource_plan']['introduced_resources']=[x for x in profile['resource_states'] if x.get('introduced')]
        self.store.put('LearningPlan',assignment['assignment_id'],profile['user_id'],
            {'rule_version':'scheduler-v1','purpose':purpose,'target_id':target['target_id'],
             'reason':reason,'profile_version':profile['profile_version']})
        self.store.put('TeachingAssignment',assignment['assignment_id'],profile['user_id'],assignment)
        return assignment,target
