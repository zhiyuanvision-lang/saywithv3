"""Bound lesson load and verify related expressions and purposeful interaction."""
import re

POLICY_VERSION = 'purposeful-speaking-v1'

def lesson_policy(stage, minutes, purpose, known_resources, reusable=None):
    # Each expression includes supported output and faded recall, not just exposure.
    count = 1 if stage == 'Pre-A1' or minutes < 8 else 3 if stage in ('B1','B2','C1','C2') and minutes >= 12 else 2
    reusable=reusable or []
    return {
        'version': POLICY_VERSION,
        'material_count': count,
        'new_expression_max': count-1 if reusable and count>1 else count,
        'reusable_expressions': reusable,
        'minimum_reuse': 1 if reusable and count>1 else 0,
        'reuse_is_mastery_evidence': False,
        'prefer_review': purpose in ('consolidation','retention','transfer') or bool(known_resources),
        'known_resource_ids': known_resources[:5],
        'selection': '围绕同一沟通目标选择不同交流动作；优先复用已学表达，避免堆叠同义说法。',
        'interaction': '引出需求→回应变化或追问→达成并确认结果；按目标选择适用环节。',
        'expected_learner_turns': [2,4] if count > 1 else [1,3],
        'turn_budget_is_soft': True,
        'feedback': '练习时建议按需展开；独立交流完成后反馈；建议不作为掌握证据。'
    }

def policy_issues(lesson, policy):
    if not policy or lesson.get('provenance',{}).get('fixture'):
        return []  # Legacy packages and deterministic single-expression fixtures stay compatible.
    issues=[]
    materials=lesson['learning_materials']
    if len(materials)!=policy['material_count']:
        issues.append(f"本次须提供{policy['material_count']}个相关表达（含复用），按课时控制练习负荷。")
    for m in materials:
        if not m.get('partner_line') or not m.get('partner_meaning_zh'):
            issues.append('每个表达须有对方上句及中文含义，以形成完整示范对话。')
    frames=[re.sub(r'[^a-z0-9_]+',' ',(m.get('hint_pattern') or m['expression']).lower()).strip() for m in materials]
    if len(frames)!=len(set(frames)):
        issues.append('表达句型重复：选择同一交流中不同动作的表达，不要只换示例值。')
    def frame(m):
        return re.sub(r'[^a-z0-9_]+',' ',(m.get('hint_pattern') or m['expression']).lower()).strip()
    familiar={frame(m) for m in policy.get('reusable_expressions',[])}
    reused=sum(frame(m) in familiar for m in materials)
    if reused<policy.get('minimum_reuse',0) or len(materials)-reused>policy['new_expression_max']:
        issues.append('应复用已接触的表达框架，并遵守新表达数量限制；换示例值仍属于复用。')
    for name in ('practice_task','independent_task'):
        task=lesson.get(name)
        if not task:continue
        flow=task['assessment_contract'].get('dialogue_flow')
        if not isinstance(flow,list) or not 1<=len(flow)<=4 or any(not isinstance(x,str) or not x.strip() for x in flow):
            issues.append(name+' 缺少1–4项dialogue_flow交流环节；它是角色对话计划，不是新增评价标准。')
        elif policy['material_count']>1 and len(flow)<2:
            issues.append(name+' 应覆盖至少两个交流环节，包括对方回应后的继续交流。')
    return issues
