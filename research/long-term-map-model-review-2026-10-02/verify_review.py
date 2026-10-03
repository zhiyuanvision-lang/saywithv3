from pathlib import Path
import json,hashlib,re
from jsonschema import Draft202012Validator
P=Path(__file__).resolve().parent;OLD=P.parent/'long-term-map-release-2026-10-02';SRC=P.parent/'long-term-map-gse-clb-2026-10-02'
def read(p):return json.loads(p.read_text())
m=read(P/'curriculum_map.json');summary=read(P/'review_summary.json');reviews=read(P/'target_review.json');relations=read(P/'alignment_review.json');nodes={x['id']:x for x in m['capability_groups']};goals={x['id']:x for x in m['learning_objectives']};refs=read(P/'gse_objectives_corrected.json')+read(SRC/'gse_grammar.json');ref_ids={x['id'] for x in refs};checklist=[]
def check(ok,name):checklist.append({'name':name,'passed':bool(ok)})
schema=read(OLD/'curriculum_map.schema.json');errors=list(Draft202012Validator(schema).iter_errors(m));check(not errors,'original_map_schema_compatible')
check(len(nodes)==140 and len(goals)==424 and len(reviews)==424,'all_groups_and_objectives_reviewed')
check({x['objective_id'] for x in reviews}==goals.keys(),'review_ids_match_map')
check(len(relations)==1315,'every_existing_group_and_child_relation_has_decision')
check(all(r['review_completed'] and not r['independent_review'] for r in reviews),'completed_single_model_review_transparent')
check(sum(r['original_outcome']!=r['reviewed_outcome'] for r in reviews)==24,'24_explicit_outcome_revisions')
for g in goals.values():
 check(g['parent_id'] in nodes,'parent:'+g['id'])
 check(g['generation_contract']['main_outcome']==g['outcome'] and g['generation_contract']['target_version']==m['version'],'generation_version:'+g['id'])
 check('旧gse_candidate_links不是生成授权池' in g['generation_contract']['source_selection'],'rejected_links_excluded:'+g['id'])
 for ref in g['reviewed_standard_references']:
  check(ref['reference_id'] in ref_ids and (P/ref['source_file']).is_file(),'verified_source:'+ref['reference_id'])
  check(not ref['official_equivalence'] and not ref['learner_score_authority'],'no_official_score_claim:'+ref['reference_id'])
 check((P/g['language_resources']['database']).exists(),'vocabulary_database:'+g['id'])
 check(g['learner_release_status']=='requires_reviewed_lesson','task_release_gate:'+g['id'])
for r in relations:check(r['decision'] in ['retain_component_reference','reject_for_this_group','reject_for_this_target','reject_unreconciled_source'] and r['official_equivalence'] is False,'terminal_relation_decision')
# Semantic regressions chosen from observed mistakes, independent of the decision counts.
def active(node,fragment):return any(fragment in r['text'] and r['model_review']['decision']=='retain_component_reference' for r in nodes[node]['gse_alignment']['candidate_objectives'])
check(not active('DESCRIBE.B1','reservation'),'reservation_changes_not_description')
check(not active('STORY.A1','order a meal'),'ordering_not_storytelling')
check(not active('SERVICE.C1','industry'),'technical_vocabulary_not_terms_verification')
check(not active('LEX.REGISTER','equivalent term'),'paraphrase_not_register')
check(not active('DISCOURSE.REFERENCE','past'),'past_time_not_anaphora')
check(not active('FORM.SPACE','preposition of time'),'temporal_prepositions_not_spatial')
check(any('registers' in r['outcome_en'] for r in goals['LEX.REGISTER.s2']['reviewed_standard_references']),'register_reference_replaced_with_actual_register')
check(any('someone else' in r['outcome_en'] for r in goals['MEDIATE.B1.s3']['reviewed_standard_references']),'mediation_reference_retains_other_person_information')
check(all(not re.search(r'\b(?:PRO|AC)\b',r['text']) for r in read(P/'gse_objectives_corrected.json')),'margin_labels_not_embedded_in_objectives')
check(all(10<=r['gse']<=90 for r in read(P/'gse_objectives_corrected.json')),'source_scores_in_range')
check(all(not n['clb_alignment']['model_review']['infer_level_from_crosswalk'] for n in nodes.values()),'clb_crosswalk_not_used_as_node_grade')
check(all('具体任务' in r['stage_review'] for r in reviews),'stage_claim_bound_to_task_conditions')
check(read(P/'release_policy.json')['public_ready'] is False,'review_not_misreported_as_full_launch')
failed=[x['name'] for x in checklist if not x['passed']];result={'status':'passed' if not failed else 'failed','checks':len(checklist),'failed':failed,'schema_errors':[e.message for e in errors],'scope':'review coverage, references, versions, deployment paths, regression decisions, release boundaries','actual_generator_or_audio_tested':False}
(P/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(bool(failed))
