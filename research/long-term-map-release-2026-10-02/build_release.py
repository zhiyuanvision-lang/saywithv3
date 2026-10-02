"""将研究草案编译为可接入后端、带发布状态的课程地图包。"""
from pathlib import Path
import json,hashlib,re,copy,collections,html,csv,sqlite3
P=Path(__file__).resolve().parent;BASE=P.parent/'long-term-map-gse-clb-2026-10-02'
def read(p):return json.loads(p.read_text())
def save(name,obj):(P/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2))
base=read(BASE/'curriculum_map.json');source_goals=read(BASE/'gse_objectives.json')
lex=read(P/'vocabulary/manifest.json')
lexrows=[json.loads(line) for line in (P/'vocabulary/gse_vocabulary.jsonl').read_text().splitlines()]
lex['gse_na_count']=sum(r.get('gse')=='N/A' for r in lexrows)
lex['gse_starred_count']=sum('*' in str(r.get('gse','')) for r in lexrows)
lex['completeness_limit']='对当前Toolkit全部GL、SSGL、YL词义查询的完整快照，含N/A未分级词义；不是Pearson未公开内部数据。音频仅保存链接。'
(P/'vocabulary/manifest.json').write_text(json.dumps(lex,ensure_ascii=False,indent=2))
with sqlite3.connect(P/'vocabulary/gse_vocabulary.sqlite') as c:
    names=[r[1] for r in c.execute('PRAGMA table_info(senses)')]
    if 'gse_raw' not in names:c.execute('ALTER TABLE senses ADD COLUMN gse_raw TEXT')
    if 'gse_status' not in names:c.execute('ALTER TABLE senses ADD COLUMN gse_status TEXT')
    c.executemany('UPDATE senses SET gse_raw=?,gse_status=? WHERE id=?',[(r['gse'],'ungraded' if r['gse']=='N/A' else 'publisher_starred' if '*' in r['gse'] else 'published',r['itemId']) for r in lexrows])
lex['sha256']['gse_vocabulary.sqlite']=hashlib.sha256((P/'vocabulary/gse_vocabulary.sqlite').read_bytes()).hexdigest()
(P/'vocabulary/manifest.json').write_text(json.dumps(lex,ensure_ascii=False,indent=2))

LEVELS=['Pre-A1','A1','A2','B1','B2','C1','C2'];BANDS={'Pre-A1':[10,21],'A1':[22,29],'A2':[30,42],'B1':[43,58],'B2':[59,75],'C1':[76,84],'C2':[85,90]}
def stage(score):return next(k for k,(a,b) in BANDS.items() if a<=score<=b)
TOPICS={
 'CONTACT':['117','303','702'], 'INFO':['513','504','459','303'],
 'DESCRIBE':['383','420','848','504'], 'NEEDS':['242','49','702'],
 'STORY':['191','513','4'], 'EXPLAIN':['191','473','4','1111'],
 'REQUEST':['117','303','112'], 'ARRANGE':['513','358','303'],
 'SERVICE':['1142','799','595','504'], 'COMPARE':['420','473','459','358'],
 'OPINION':['242','49','358','4'], 'RELATE':['117','49','702'],
 'COLLAB':['1213','303','4'], 'REPAIR':['303','358','4'],
 'LISTEN':['513','459','303','4'], 'MEDIA':['898','4'],
 'PHONE':['303','799','513'], 'MEDIATE':['4','303','358'],
 'SOUND':['527'],'LEX':['527','303'],'FORM':['527','473'],'DISCOURSE':['4','473'],'STRATEGY':['4','303'],
}
SPLITS={
 'REQUEST.A2.s2':[('accept','接受邀请'),('decline','婉拒邀请')],
 'RELATE.A1.s1':[('express','表达感谢'),('respond','回应感谢')],
 'RELATE.A1.s2':[('express','表达道歉'),('respond','回应道歉')],
 'RELATE.A1.s3':[('express','表达祝贺'),('respond','回应祝贺')],
}
# 这些是共享动作的导航关系；不把相似动作直接视为同一掌握证据。
SHARED_ACTS={
 'decline':['REQUEST.A2.s2.decline','RELATE.A2.s1'],
 'confirm_arrangement':['ARRANGE.A1.s3','ARRANGE.A2.s3','INFO.A1.s3'],
 'clarify_information':['REPAIR.A2.s1','INFO.B1.s3','LISTEN.B1.s3'],
}
nodes={n['id']:copy.deepcopy(n) for n in base['nodes']}
old_children={c['id']:c for c in base['subtargets']};objectives=[];migrations={};review=[]
for n in nodes.values():
    oid=n['id'];support=n['type']!='communication'
    n['kind']='support_track' if support else 'capability_group'
    n['reference_stage']=n.pop('level_candidate')
    n['level_status']='产品课程阶段参考；尚未通过外部测评校准，不报告用户正式CEFR/GSE成绩'
    if support:
        n['introduced_at']=n['reference_stage'];n['applicable_stages']=LEVELS
        n['task_blueprint']['difficulty_by_stage']='按承载的沟通目标选择；不固定在introduced_at'
    n['learning_objective_ids']=[]
    n['standard_alignment_release_status']='reference_only'
    n['gse_alignment']['runtime_authority']=False
    for ref in n['gse_alignment']['candidate_objectives']:
        ref['source_file']='../long-term-map-gse-clb-2026-10-02/'+ref['source_file']
    n['clb_alignment']['runtime_authority']=False
    n['clb_alignment']['runtime_usage']='用于选择条件参考；不能据候选CLB等级报告学习者已达该等级'
    for oldid in n['subtarget_ids']:
        original=old_children[oldid];parts=SPLITS.get(oldid,[(None,original['outcome'])])
        newids=[]
        for suffix,label in parts:
            targetid=oldid+('.'+suffix if suffix else '');newids.append(targetid)
            target=copy.deepcopy(original);target['id']=targetid;target['outcome']=label
            target['reference_stage']=target.pop('cefr_candidate')
            target['kind']='support_objective' if support else 'communication_objective'
            target['applicable_stages']=LEVELS if support else [target['reference_stage']]
            target['curriculum_status']='specified'
            target['learner_release_status']='requires_reviewed_lesson'
            target['source_alignment_status']='reference_candidates_not_certified'
            target['required_background']='任务提供必要事实和关系；不把专业知识、性格、文化偏好作为语言掌握'
            target['completion_unit']='objective_with_task_conditions'
            target['assessment_check']={
             'pass':f'在任务明确的条件与允许支持范围内，完成“{label}”，关键意义与意图清楚；任何正确改述均可',
             'partial':'完成部分关键意义，或需要超出独立检查允许范围的提示；具体记录证据',
             'fail':'在可判定的有效任务中，关键意义错误或无法完成必要沟通动作',
             'unjudgeable':'音频/识别低可信、事实或脚本不完整、角色替用户完成关键动作、评分不能确定',
            }
            target['language_resources']={'database':'vocabulary/gse_vocabulary.sqlite','audiences':['GL','SSGL'],'topic_root_ids':TOPICS[n['family_id']],'gse_reference_band':BANDS[n['reference_stage']],'selection_policy':'按词义ID排除用户已掌握资源；主题筛选只是候选，必须核查此任务是否需要该词义','ungraded_policy':'N/A不能自动归级；通过审核后可作必要资源','starred_policy':'保留出版社星号状态，不把它当作确定的任务难度','yl_policy':'成人默认不选YL；若亲子情境需要，明确开启并单独记录','audio_policy':'使用已授权来源声音或审核后的合成声音；当前词库只存音频URL'}
            target['generation_contract']['main_outcome']=label
            target['generation_contract']['target_version']='1.0.0-rc1'
            target['generation_contract']['standard_policy']='未核查的候选不能改写学习目标或给用户赋标准分数；使用原创目标可生成候选内容，但须经任务质检'
            target['generation_contract']['requires_concrete_fields']=['learner_prompt','partner_private_facts','scenario_facts','role_response_rules','critical_meanings','acceptable_outcomes','allowed_support','difficulty_axes','assessment_anchor_examples','independent_variant','audio_text_consistency']
            target['mastery_rule']={'state_values':['unseen','supported','independent','transferred','retained'],'state_storage':'保留分条件证据，不只存一个布尔值','event_requirements':['音频证据或有效行动','具体任务与版本','支持量','关键意义判断','评分可信度'],'retention_failure':'保留历史成功证据；降低当前可信度并安排补练','time_policy':'不将固定次数、分钟数或复习间隔当作已验证最优值','official_score_policy':'课程掌握状态不是正式CEFR/GSE测评分数'}
            objectives.append(target);n['learning_objective_ids'].append(targetid)
        migrations[oldid]={'new_ids':newids,'evidence_transfer':'原复合目标的总成功标记不能自动分给拆分后的子目标；需依据旧音频核查各沟通动作' if len(parts)>1 else '保留目标ID；原证据需携带任务条件和支持记录'}
    n.pop('subtarget_ids',None)
    n['task_design']['independent_subtargets']=n['learning_objective_ids']
    review.append({'node_id':oid,'actions':['保留原目标与阶段索引','子目标不再强制三个','标准候选只供参考','补充词义级资源查询','发布必须有审核后的具体任务'],'split_old_ids':[i for i in old_children if i in SPLITS and old_children[i]['parent_id']==oid],'support_stage_policy':'贯穿各阶段，旧阶段改为首次引入参考' if support else '按任务条件判断阶段，不按单次成功跨层推断','validation_status':'完成产品数据规则检查；外部课程评审和真人校准仍待完成'})

# 原文同技能、同分数目标跨套去重；不同分数仍分别保留，不做平均。
catalog=collections.defaultdict(list)
for r in source_goals:
    if r['skill'] in ['Listening','Speaking']:catalog[(r['skill'],r['gse'],r['text'])].append(r)
official_goals=[]
for (skill,score,text),refs in sorted(catalog.items()):
    goalid='GSE.'+hashlib.sha256(f'{skill}|{score}|{text}'.encode()).hexdigest()[:16]
    official_goals.append({'id':goalid,'outcome_en':text,'skill':skill,'gse':score,'cefr_reference':stage(score),'audiences':sorted(set(r['source'].split('.')[-1] for r in refs)),'source_refs':[{'source_record_id':r['id'],'file':'../long-term-map-gse-clb-2026-10-02/'+r['source_file'],'pdf_page':r['pdf_page']} for r in refs],'usage':'可作标准目标原文参考；具体教学与测评仍需任务脚本，不自动替代原创地图目标','source_status':'published_objective','learner_release_status':'requires_reviewed_lesson'})
save('official_oral_objectives.json',official_goals)

edge=[]
for n in nodes.values():
    for earlier in n.get('recommended_before',[]):edge.append({'from':earlier,'to':n['id'],'type':'recommended_progression','hard_requirement':False})
    for support in n.get('support_candidates',[]):edge.append({'from':support,'to':n['id'],'type':'on_demand_support','trigger':'实际失败证据','hard_requirement':False})
goalids={g['id'] for g in objectives}
for action,members in SHARED_ACTS.items():
    members=[x for x in members if x in goalids]
    edge.append({'type':'shared_communication_action','action':action,'objective_ids':members,'mastery_propagation':False,'policy':'用于复习和迁移推荐；逐个检查新任务条件后才更新对应证据'})

release_policy={
 'version':'1.0.0-rc1','public_ready':False,'backend_data_ready':True,
 'mandatory_gates':[
  {'id':'MAP_DATA','scope':'地图数据','status':'pending_validation','requirement':'schema、引用、版本、迁移和资源完整性检查通过'},
  {'id':'TASK_REVIEW','scope':'用户可见任务','status':'not_completed','requirement':'每个发布任务具备双方事实、响应规则、关键意义、难度和审核后的评分样例'},
  {'id':'GENERATOR_QA','scope':'AI动态内容','status':'not_completed','requirement':'用当前实际模型与语音链路验证内容自然度、难度、信息一致性及答案隔离'},
  {'id':'SCORER_CALIBRATION','scope':'自动诊断与判掌握','status':'not_completed','requirement':'有效音频与人工锚点比较，低可信度不更新掌握'},
  {'id':'LEARNER_PILOT','scope':'长期教学承诺','status':'not_completed','requirement':'真实目标用户的陌生任务表现与延迟保持检查；不预先承诺最快路径'},
 ],
 'decision':'先接入后端并制作审核任务；只有完成发布检查的目标才能进入用户课程。全量自动上线不能由结构校验代替教学审核。',
}
mapout={
 'schema_version':'1.0','version':'1.0.0-rc1','status':'release_candidate','audience':'中国大陆高中及以上教育的成人，以大学生和初入职场者为初版目标','authorization_assumption':'依用户指示视为授权已通过；未审阅授权文件',
 'objective':'在需要的情境中独立、可理解、适切地持续交流；用迁移与保持证据衡量进步',
 'count_policy':'不固定140节点或每节点三个子目标；本次保留兼容索引，目标数由覆盖、边界和评价要求决定',
 'levels':{'labels':LEVELS,'usage':'课程阶段参考，非正式测试判级','gse_bands':BANDS},
 'families':base['families'],'capability_groups':list(nodes.values()),'learning_objectives':objectives,
 'relations':edge,'routes':base['routes'],'task_bundles':base.get('task_bundles',[]),'standard_goal_catalog':'official_oral_objectives.json',
 'standard_reference_catalogs':{'gse_records':'../long-term-map-gse-clb-2026-10-02/gse_objectives.json','gse_grammar':'../long-term-map-gse-clb-2026-10-02/gse_grammar.json','clb_conditions':'../long-term-map-gse-clb-2026-10-02/clb_conditions.json','clb_gse_official_links':'../long-term-map-gse-clb-2026-10-02/official_clb_gse_links.json'},
 'lexicon':{'manifest':'vocabulary/manifest.json','database':'vocabulary/gse_vocabulary.sqlite','jsonl':'vocabulary/gse_vocabulary.jsonl','csv':'vocabulary/gse_vocabulary.csv','rows':lex['exported_total'],'na_rows':lex['gse_na_count'],'starred_rows':lex['gse_starred_count']},
 'release_policy':'release_policy.json','source_map_sha256':hashlib.sha256((BASE/'curriculum_map.json').read_bytes()).hexdigest(),
}
save('curriculum_map.json',mapout);save('migration.json',migrations);save('node_review.json',review);save('release_policy.json',release_policy)

schema={
 '$schema':'https://json-schema.org/draft/2020-12/schema',
 '$id':'saywith:curriculum-map:1.0','type':'object',
 'required':['schema_version','version','status','levels','capability_groups','learning_objectives','relations','lexicon','release_policy'],
 'properties':{
  'schema_version':{'const':'1.0'},'version':{'type':'string'},
  'status':{'enum':['release_candidate','released']},
  'capability_groups':{
   'type':'array','items':{
    'type':'object','required':['id','kind','reference_stage','learning_objective_ids'],
    'properties':{
     'id':{'type':'string'},'kind':{'enum':['capability_group','support_track']},
     'reference_stage':{'enum':LEVELS},
     'learning_objective_ids':{'type':'array','minItems':1,'uniqueItems':True,'items':{'type':'string'}},
    },
   },
  },
  'learning_objectives':{
   'type':'array','items':{
    'type':'object',
    'required':['id','parent_id','outcome','reference_stage','assessment_check','generation_contract','language_resources','mastery_rule','learner_release_status'],
    'properties':{'id':{'type':'string'},'outcome':{'type':'string','minLength':2},'reference_stage':{'enum':LEVELS},'learner_release_status':{'enum':['requires_reviewed_lesson','published']}},
   },
  },
 },
}
save('curriculum_map.schema.json',schema)

runtime={
 'selection':['检查任务是否获准发布','读取学习者分维度、分词义与分任务条件证据','先处理阻断沟通的缺口与应复习目标','从相关路线选择一个主目标及必要支持点','选择匹配词义，不按词形推断掌握','生成后核查任务与独立测评变体'],
 'learner_state_schema':{'objective_evidence':['objective_id','target_version','task_id','condition_signature','support_used','audio_ref','observable_results','confidence','timestamp'],'sense_state':['sense_id','recognized','retrievable','flexible_use','last_evidence'],'speed_state':['session_duration','completion_difficulty','fatigue_feedback','delayed_retention']},
 'never':['仅因学习等级升高而自动掌握全部低阶目标','将转写字数当流畅度','将正确朗读当自由互动能力','将候选标准对应当官方认证','将N/A当0分词','将整段对话练完当全部目标掌握','跨目标无条件复制成功标记'],
 'release_decision':'通过审核的具体任务进入生成池；候选库与用户课程库分开。没有审核模板时停止发布该任务，不虚构回退模板。',
}
save('runtime_policy.json',runtime)

# 用于后端正反例校验的具体任务，语音和教学审核仍是发布门槛。
fixture={
 'id':'ARRANGE.A2.fixture.1','version':'1','objective_ids':['ARRANGE.A2.s1','ARRANGE.A2.s2','ARRANGE.A2.s3'],
 'learner_prompt':'你要和同伴在图书馆见面。你下午4:30或6:00有空，请商定双方能参加的时间。',
 'learner_facts':{'available':['16:30','18:00']},'partner_private_facts':{'available':['15:00','16:30'],'location':'library'},
 'initial_partner_offer':'15:00','required_actions':['说明15:00不可用','提出可行时间','确认双方接受的时间地点'],
 'acceptable_outcomes':[{'time':'16:30','location':'library'}],
 'role_response_rules':['只按对方已提出问题提供信息','接受16:30和library组合','不直接告诉用户完整最终答案','允许请求重复'],
 'allowed_support':{'independent':['task_prompt','reasonable_clarification'],'prohibited':['model_answer','sentence_completion']},
 'assessment_anchors':{'pass':'说明冲突，协商并确认16:30/library；不要求特定英语句式','partial':'得到可行时间但未核查地点或未明确确认','fail':'坚持18:00且未解决对方不可用','unjudgeable':'音频不能可靠识别或伙伴提前给出完整答案'},
 'independent_variant':{'learner_available':['10:00','14:00'],'partner_available':['11:00','14:00'],'partner_location':'park','acceptable_outcomes':[{'time':'14:00','location':'park'}]},
 'publication_status':'requires_audio_and_task_review',
}
save('task_fixture.json',fixture)

with (P/'learning_objectives.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['id','parent_id','reference_stage','kind','outcome','learner_release_status'])
 for g in objectives:w.writerow([g[k] for k in ['id','parent_id','reference_stage','kind','outcome','learner_release_status']])

audit={'optimized_group_count':len(nodes),'learning_objective_count':len(objectives),'source_oral_objectives_deduplicated':len(official_goals),'changes':[
 '复合的接受/拒绝及礼貌行为拆分，取消每节点恰好三个的约束',
 '发音、词汇提取和策略改为全阶段支持，首次引入阶段不限制能力适用范围',
 '重复动作增加共享关系，禁止自动复制掌握证据',
 '标准候选与出版社原文分开，运行时不把候选当等级认证',
 '词义级资源接入，保留N/A与星号，成人默认排除YL资源',
 '每个目标建立明确的判断状态、具体任务字段和版本迁移',
 '增加发布检查，数据接入与全量课程发布分别判断',
 ],'unresolved':['目标语义边界与等级需独立课程评审','除样例外，具体课程与评分样例库未完成','实际模型/语音链路的生成和评分未验证','真人长期保持与迁移未验证'],'conclusion':'后端数据包已编译；全部课程公开上线的最终审核尚未完成'}
save('optimization_audit.json',audit)
esc=html.escape
cards=[]
for n in nodes.values():
 gs=[g for g in objectives if g['parent_id']==n['id']]
 cards.append('<details><summary>'+esc(n['id']+' · '+n['label'])+'</summary><p>阶段参考：'+esc(n['reference_stage'])+('；支持能力贯穿全部阶段' if n['kind']=='support_track' else '')+'</p><ol>'+''.join('<li>'+esc(g['outcome'])+'</li>' for g in gs)+'</ol><p>词义主题：'+', '.join(TOPICS[n['family_id']])+'；发布状态：需审核后的具体课程。</p></details>')
report=f'''<!doctype html><html lang="zh"><meta charset="utf-8"><title>长期课程地图与完整GSE词义导出</title><style>body{{font:16px/1.7 system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#223}}details{{padding:12px;border:1px solid #ccd;margin:10px 0;border-radius:8px}}summary{{cursor:pointer;font-weight:bold}}a{{color:#235caa}}.note{{padding:16px;background:#fff2d8;border-radius:10px}}table{{border-collapse:collapse}}td,th{{border:1px solid #ccd;padding:10px}}</style><h1>长期课程地图 1.0.0-rc1</h1><div class="note"><b>状态：后端接入包 / 上线候选</b><p>词义数据完整导出；地图结构、资源及发布规则已优化。尚未完成全部具体课程审核、语音评分校准和真实用户试验，不能把本版称为已验证的全量上线最终课程。</p></div><h2>GSE词义导出</h2><p>{lex['exported_total']:,} 个唯一词义，与接口总数一致。成人通用 34,794；成人软技能 3,513；少儿 3,095。含 {lex['gse_na_count']} 个N/A、{lex['gse_starred_count']} 个星号词义，保留原状态。音频仅保存链接。</p><p><a href="vocabulary/gse_vocabulary.csv">词义CSV</a> · <a href="vocabulary/gse_vocabulary.jsonl">词义JSONL</a> · <a href="vocabulary/gse_vocabulary.sqlite">后端SQLite</a> · <a href="vocabulary/manifest.json">完整性清单</a></p><h2>地图优化</h2><p>{len(nodes)} 个兼容能力分组，{len(objectives)} 个学习目标；{len(official_goals)} 个去重后的官方听说目标供参考。数量不固定。</p><ul>{''.join('<li>'+esc(x)+'</li>' for x in audit['changes'])}</ul><p><a href="curriculum_map.json">地图JSON</a> · <a href="learning_objectives.csv">学习目标CSV</a> · <a href="release_policy.json">发布检查</a> · <a href="verification.json">验证结果</a> · <a href="README.md">使用说明</a></p><h2>逐节点</h2>{''.join(cards)}</html>'''
(P/'report.html').write_text(report)
print(json.dumps({'groups':len(nodes),'objectives':len(objectives),'official_oral_goals':len(official_goals),'vocabulary':lex['exported_total'],'public_ready':False},ensure_ascii=False))
