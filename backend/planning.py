"""Rule-based scheduling and concrete teaching assignments."""
import re
import time
from .contracts import TeachingAssignment
from .store import uid

STAGES=['Pre-A1','A1','A2','B1','B2','C1','C2']

class Planner:
    def __init__(self,curriculum,store):self.curriculum=curriculum;self.store=store

    def plan(self,profile,request):
        states={x['target_id']:x for x in profile['target_states']}
        stage=profile['preferences'].get('reference_stage','A2')
        if stage not in STAGES:stage='A2'
        explicit=request.get('target_id')
        purpose='new';reason='扩展当前难度下尚未训练的交流能力'
        if explicit:
            target=self.curriculum.target(explicit);reason='用户选择此沟通目标'
        else:
            candidates=self.curriculum.list_targets(stage=stage)
            # Move the practice band only after every goal in the current band has
            # repeated independent and transfer evidence; this is not certification.
            while candidates and all(states.get(t['target_id'],{}).get('independent')=='demonstrated'
                                     and states.get(t['target_id'],{}).get('transfer')=='demonstrated' for t in candidates):
                index=STAGES.index(stage)
                if index==len(STAGES)-1:break
                higher=self.curriculum.list_targets(stage=STAGES[index+1])
                if not higher:break
                # Overdue practice across previously completed bands remains eligible.
                if any(states.get(t['target_id'],{}).get('due_at',float('inf'))<=time.time() for t in candidates):break
                stage=STAGES[index+1];candidates=higher
            now=time.time()
            priorities=[]
            for t in candidates:
                s=states.get(t['target_id'],{})
                due=s.get('due_at',float('inf'))<=now
                family=t['target_id'].split('.')[0]
                coverage=sum(1 for x in states if x.startswith(family+'.'))
                need=0 if due else 1 if s.get('independent') in ('needs_practice','supported') else 2 if not s else 3
                priorities.append((need,coverage,t['target_id']))
            if not priorities:raise ValueError('No targets at requested stage')
            id=min(priorities)[2];target=self.curriculum.target(id)
        state=states.get(target['target_id'],{})
        if state.get('independent') in ('needs_practice','supported'):purpose='consolidation';reason='此前表现仍需要帮助，先减少提示完成此目标'
        elif state.get('due_at',float('inf'))<=time.time():purpose='retention';reason='之前完成过此目标，现在检查隔期是否仍能完成'
        elif state.get('independent')=='demonstrated' and state.get('transfer')!='demonstrated':purpose='transfer';reason='已有独立完成证据，换条件验证是否能应用'
        elif not state:purpose='diagnostic';reason='目前没有此目标的表现证据，先检查起点'
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
            completion_standard=target['outcome'],minutes=request.get('minutes',10)).model_dump()
        assignment['resource_plan']['introduced_resources']=[x for x in profile['resource_states'] if x.get('introduced')]
        self.store.put('LearningPlan',assignment['assignment_id'],profile['user_id'],
            {'rule_version':'scheduler-v1','purpose':purpose,'target_id':target['target_id'],
             'reason':reason,'profile_version':profile['profile_version']})
        self.store.put('TeachingAssignment',assignment['assignment_id'],profile['user_id'],assignment)
        return assignment,target
