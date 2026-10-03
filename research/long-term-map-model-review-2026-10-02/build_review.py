from pathlib import Path
import json,copy,csv,hashlib,collections,re
from review_decisions import ALIGN,ADD,REWRITE,NODE_NOTES,FAMILY_CONDITIONS,OVERLAP
P=Path(__file__).resolve().parent;OLD=P.parent/'long-term-map-release-2026-10-02';SRC=P.parent/'long-term-map-gse-clb-2026-10-02'
def read(p):return json.loads(p.read_text())
def save(name,obj):(P/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
m=read(OLD/'curriculum_map.json');original=copy.deepcopy(m);VERSION='1.0.1-model-reviewed';m['version']=VERSION;m['status']='release_candidate'
records=read(P/'gse_objectives_corrected.json');grammar=read(SRC/'gse_grammar.json')
for r in grammar:r['skill']='Grammar';r['source_file']='../long-term-map-gse-clb-2026-10-02/'+r['source_file']
refs={id:r for r in records for id in [r['id']]+r.get('legacy_alias_ids',[])};refs.update({r['id']:r for r in grammar})
clb={r['id']:r for r in read(SRC/'clb_conditions.json')}
goals={g['id']:g for g in m['learning_objectives']};nodes={n['id']:n for n in m['capability_groups']};target_reviews=[];relation_reviews=[];node_reviews=[]
assert set(ALIGN)==set(nodes), 'All groups require an explicit reviewer decision'
for n in m['capability_groups']:
 id=n['id'];decisions=ALIGN[id];assert len(decisions)==len(n['learning_objective_ids']),id
 used={i for row in decisions for i in row};candidates=n['gse_alignment']['candidate_objectives'];node_accepted=[]
 note=NODE_NOTES.get(id,'只采用与本节点具体沟通动作相关的部分参考；不把一个条目覆盖为整组目标。')
 for i,r in enumerate(candidates):
  source=refs.get(r['objective_id']);accepted=i in used and source is not None
  status='retain_component_reference' if accepted else ('reject_unreconciled_source' if source is None else 'reject_for_this_group')
  row={'scope':'group','node_id':id,'reference_id':r['objective_id'],'canonical_reference_id':source['id'] if source else None,'target':n['outcome'],'source_text':source['text'] if source else r['text'],'decision':status,'reason':note if not accepted else '在逐子目标决策矩阵中被采用；仅参考共同动作与已写明的源条件，整组范围未被该条目完整覆盖。','official_equivalence':False}
  relation_reviews.append(row);r['model_review']=row;r['source_metadata_status']='verified_source_catalog' if source else 'quarantined_unreconciled';r['runtime_authority']=False
  if source:
   for k in ['gse','skill','text','pdf_page','source_file']:r[k]=source[k]
   a,b=m['levels']['gse_bands'][n['reference_stage']];r['level_conflict']=not a<=source['gse']<=b
  if accepted:node_accepted.append(source['id'])
 n['gse_alignment']['reviewed_reference_ids']=list(dict.fromkeys(node_accepted));n['gse_alignment']['status']='单一模型已完成采纳/拒绝审核；保留关系为部分参考，不是标准等价'
 n['standard_alignment_release_status']='model_reviewed_reference_only';n['publication_status']='model_reviewed_map_requires_task_QA'
 n['conditions']['required_facts']=FAMILY_CONDITIONS[n['family_id']][0]
 n['assessment']['status']='目标与评判边界经单一模型审核；具体音频和评分器未实测'
 n['clb_alignment']['model_review']={'decision':'condition_reference_only','reason':'CLB原文可提供输入、支持、场合与互动条件；旧基准候选不能经GSE链式推导为本节点等级。','official_equivalence':False,'infer_level_from_crosswalk':False,'source_pages_exist':all(x in clb for x in n['clb_alignment']['condition_source_ids'])}
 n['task_blueprint']['seed_usage_policy']='仅作选题素材；按本次子目标选择所需事实。低阶任务不强制加入近期经历、多条件冲突或其他子目标。'
 n['task_blueprint']['difficulty_status']='产品设计参数，经模型检查适配原则；具体生成任务仍须验证，不是CEFR/CLB官方等价。'
 n['review_required']=['实际课程与角色脚本自动质检','实际语音/评分模型验证','真实使用证据与延迟保持检查']
 for position,gid in enumerate(n['learning_objective_ids']):
  g=goals[gid];before=g['outcome'];g['outcome']=REWRITE.get(gid,before)
  selected=[]
  for i in decisions[position]:
   assert 0<=i<len(candidates),(id,i)
   r=refs.get(candidates[i]['objective_id'])
   if r:selected.append(r)
  for rid in ADD.get(gid,[]):
   assert rid in refs,(gid,rid);selected.append(refs[rid])
  selected=list({s['id']:s for s in selected}.values());ids={s['id'] for s in selected}
  # Record a decision for every original child relation; selection is from model-authored matrix, not keyword scoring.
  child_relations=[]
  for link in g.get('gse_candidate_links',[]):
   ref=refs.get(link['objective_id']);canonical=ref['id'] if ref else None
   decision='retain_component_reference' if canonical in ids else ('reject_unreconciled_source' if ref is None else 'reject_for_this_target')
   row={'scope':'target','objective_id':gid,'reference_id':link['objective_id'],'canonical_reference_id':canonical,'target':g['outcome'],'source_text':ref['text'] if ref else None,'decision':decision,'reason':f'本次动作是“{g["outcome"]}”。'+('该原文只提供共同动作或语言条件的部分参考，不能代替独立任务检查。' if canonical in ids else '没有在逐目标语义决策中被采纳；不能因词面重合、父节点相关或分数邻近就认定覆盖此动作。'),'official_equivalence':False}
   link['model_review_decision']=decision;link['runtime_authority']=False;relation_reviews.append(row);child_relations.append(row)
  a,b=m['levels']['gse_bands'][g['reference_stage']]
  reviewed=[]
  for s in selected:
   text=s['text'];support='given a model' in text or 'fixed expressions' in text or 'supported by' in text or 'given help' in text
   outside=not a<=s['gse']<=b
   reviewed.append({'reference_id':s['id'],'outcome_en':text,'skill':s['skill'],'gse':s['gse'],'source_file':s['source_file'],'pdf_page':s['pdf_page'],'relation':'component_reference','review_decision':'adopt_partial_reference','shared_action':g['outcome'],'limits':'原文的对象、语境、允许帮助和范围必须保留；本原创目标的附加动作、迁移与保持不能从条目推导。','source_has_support_condition':support,'outside_reference_stage':outside,'allowed_usage':'resource_or_advanced_reference' if outside else 'lesson_design_reference','official_equivalence':False,'learner_score_authority':False})
  g['reviewed_standard_references']=reviewed;g['gse_mapping_status']='模型审核后的部分参考' if reviewed else '模型审核后保留原创目标；无已采纳对应'
  if g['kind']=='support_track':pass
  family=n['family_id'];facts,success=FAMILY_CONDITIONS[family]
  modality='audio_comprehension' if family in ['LISTEN','MEDIA'] else 'spoken_interaction'
  if family=='SOUND':modality='audio_perception_and_production'
  if gid=='INFO.Pre-A1.s2':modality='audio_comprehension'
  receptive=modality=='audio_comprehension';conditions=list(g['clb_condition_source_ids'])
  if receptive:
   benches=n['clb_alignment']['candidate_benchmarks'];conditions=[c['id'] for c in clb.values() if c['skill']=='Listening' and c['benchmark'] in benches]
  g['clb_condition_source_ids']=conditions
  g['assessment_check']={
   'pass':f'在本次明确的事实、角色与允许帮助下完成“{g["outcome"]}”，有相应回应/行动或语言证据；接受正确改述。',
   'partial':'必要意义尚缺一项，或依赖完整答案/句子补全；记录缺项及帮助，不把小语法错误直接记失败。',
   'fail':'在证据可判定时，本子目标必需意义被表达成相反意思，或未做出其必要动作。主观选择、观点、关系边界和不知道专业知识本身不算失败。',
   'unjudgeable':'音频/识别不可靠、任务不可完成、角色已给完整答案、评分不能区分正确理解与猜测，或没有本维度所需的模态证据。'}
  g['generation_contract']['main_outcome']=g['outcome'];g['generation_contract']['target_version']=VERSION;g['generation_contract']['assessment_check']=copy.deepcopy(g['assessment_check'])
  g['generation_contract']['source_selection']='只从reviewed_standard_references按允许用途选参考；没有对应时按原创目标生成。旧gse_candidate_links不是生成授权池。'
  g['generation_contract']['standard_policy']='保留出版社条目的支持、对象与范围；跨阶段只作资源/进阶参考，不自动抬高本次任务难度。CLB为条件参考，不据此给用户赋等级。'
  g['generation_contract']['task_specific_contract']={'observable_action':g['outcome'],'required_facts':facts,'success_boundary':success,'modality':modality,'critical_meaning_scope':'只判断本子目标所需意义；不能因为整场任务别处出错而否定已完成动作','independent_evidence':'答案不可见；允许任务本身合理的澄清。带示范的源条目不能直接当独立掌握证据。','must_materialize_before_use':['实际双方事实和私有信息','可行结果或开放立场范围','本目标必要意义逐项清单','对话证据位置','至少一个部分完成及意义反转例','可完成且不泄题的独立变体'],'fluency':'无音频/时序不评发音与流畅度；不以转写长度或朗读成功替代'}
  g['curriculum_status']='model_reviewed_specification';g['learner_release_status']='requires_reviewed_lesson';g['source_alignment_status']='model_reviewed_partial_references_not_certified'
  g['calibration_contract_ref']='target_review.json#'+gid
  # The map references the existing vocabulary snapshot; no duplicate corpus needed.
  g['language_resources']['database']='../long-term-map-release-2026-10-02/vocabulary/gse_vocabulary.sqlite'
  decision='revise_and_accept_specification' if gid in REWRITE else 'accept_specification_with_task_conditions'
  review={'objective_id':gid,'node_id':id,'original_outcome':before,'reviewed_outcome':g['outcome'],'decision':decision,'clarity_reason':'已把不可直接观察的内部判断改为回应、复述、说明或追问。' if gid in REWRITE else '目标有可区分的沟通动作；结合本次事实与允许帮助检查，不要求固定英语句式。','atomicity':'一个主动作或紧密相连的沟通过程；具体测评须逐项列出必要意义，不能一次通过自动掌握全部能力。','stage_review':'保留为产品课程阶段，复杂度须在具体任务中落实；本次未验证CEFR等价或先修最优顺序。','overlap_review':'不同节点的相似动作按情境和证据区分；同一次证据保留同一ID，不重复计数，不自动跨目标赋掌握。','standard_references':reviewed,'clb_review':{'decision':'task_condition_reference_only','source_ids':conditions,'modality':modality,'benchmark_equivalence':False},'task_conditions':g['generation_contract']['task_specific_contract'],'assessment_check':g['assessment_check'],'release_decision':'specification_ready_for_generator_QA','review_completed':True,'reviewer_type':'single_assistant_model','independent_review':False}
  target_reviews.append(review)
 node_reviews.append({'node_id':id,'model_review_completed':True,'decision':'retain_group_navigation','review_notes':note,'objectives_reviewed':len(decisions),'accepted_partial_reference_ids':list(dict.fromkeys(node_accepted)),'clb_conditions_reviewed_as_reference':True,'official_level_equivalence':False})
# Avoid unresolved references to a sibling vocabulary path when this reviewed map is consumed.
m['standard_reference_catalogs']['gse_records']='gse_objectives_corrected.json';m['standard_goal_catalog']='official_oral_objectives.json'
for key,value in m['lexicon'].items():
 if isinstance(value,str) and value.startswith('vocabulary/'):m['lexicon'][key]='../long-term-map-release-2026-10-02/'+value
for n in m['capability_groups']:n['language_resources']['database']='../long-term-map-release-2026-10-02/vocabulary/gse_vocabulary.sqlite'
m['model_review']={'report':'review_summary.json','targets':'target_review.json','references':'alignment_review.json','reviewer':'single_assistant_model','independent_review':False,'completed_scope':['140个分组与424个目标的语义/可观察性','全部既有GSE候选的采纳或拒绝决策','CLB作为条件参考的边界与模态选择','任务事实、公平评分和证据更新规则'],'excluded_scope':['全部词义的逐条教学审核','424套实际课程','实际生成器/ASR/口语评分服务','真人水平与学习效果']}
m['release_policy']='release_policy.json';save('curriculum_map.json',m);save('target_review.json',target_reviews);save('node_review.json',node_reviews);save('alignment_review.json',relation_reviews)
save('overlap_review.json',[{'objectives':[a,b],'reason':reason,'automatic_mastery_transfer':False,'shared_evidence_must_deduplicate':True} for a,b,reason in OVERLAP])
counts=collections.Counter(r['decision'] for r in relation_reviews)
save('review_summary.json',{'status':'completed_model_assisted_review','version':VERSION,'groups_reviewed':len(nodes),'targets_reviewed':len(target_reviews),'targets_reworded':len(REWRITE),'existing_relations_reviewed':len(relation_reviews),'reference_decisions':dict(counts),'targets_with_adopted_partial_reference':sum(bool(r['standard_references']) for r in target_reviews),'targets_without_adopted_reference':sum(not r['standard_references'] for r in target_reviews),'new_reference_assignments':sum(len(x) for x in ADD.values()),'source_audit':{k:v for k,v in read(P/'source_calibration_audit.json').items() if k in ['original_rows','coordinate_rows','corrected_existing_rows','original_rows_not_reconciled']},'completed_review_is_not_public_release':True,'independent_review':False,'public_ready':False,'remaining_checks':['具体课程及独立变体自动质检','实际大模型与语音评分链路测试','真实使用证据与延迟保持检查'],'review_method':'助手读取全量分组、子目标和既有候选原文，手工编写review_decisions.py中的逐目标决策矩阵；build_review.py落实决策并记录每条关系。不是关键词分数达到阈值就算语义审核。'})
policy=read(OLD/'release_policy.json');policy['version']=VERSION;policy['model_assisted_map_review']={'status':'completed','evidence':'review_summary.json','scope':'地图目标与候选对应；不代替具体课程/语音测评'};policy['public_ready']=False
for gate in policy['mandatory_gates']:
 if gate['id']=='SCORER_CALIBRATION':gate['requirement']='模型锚点与实际语音评分器对照；积累真实使用证据，低可信度不更新掌握。无需先配置人工团队，但不能把合成证据等同真人校准。'
policy['decision']='地图规格完成模型审核，可以制作并检查具体课程；实际内容、评分与学习效果门槛继续按证据判定。';save('release_policy.json',policy)
with (P/'target_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['目标ID','原目标','审核后目标','审核决定','已采纳参考数量','CLB用途','用户课程状态'])
 for r in target_reviews:w.writerow([r['objective_id'],r['original_outcome'],r['reviewed_outcome'],r['decision'],len(r['standard_references']),'条件参考；非等级等价','需具体课程质检'])
print(json.dumps(read(P/'review_summary.json'),ensure_ascii=False,indent=2))
