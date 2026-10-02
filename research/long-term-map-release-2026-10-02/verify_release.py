from pathlib import Path
import json,csv,hashlib,sqlite3,re,collections
from jsonschema import Draft202012Validator
P=Path(__file__).resolve().parent
def read(f):return json.loads((P/f).read_text())
errors=[];checks=[]
def check(ok,name):
    checks.append({'check':name,'passed':bool(ok)})
    if not ok:errors.append(name)
m=read('curriculum_map.json');v=read('vocabulary/manifest.json');policy=read('release_policy.json')
schema=read('curriculum_map.schema.json');errs=list(Draft202012Validator(schema).iter_errors(m))
check(not errs,'课程地图JSON Schema')
groups={x['id']:x for x in m['capability_groups']};goals={x['id']:x for x in m['learning_objectives']}
check(len(groups)==len(m['capability_groups']),'能力分组ID唯一')
check(len(goals)==len(m['learning_objectives']),'学习目标ID唯一')
check(all(x['parent_id'] in groups for x in goals.values()),'学习目标父节点存在')
check(all(set(x['learning_objective_ids'])<=goals.keys() and x['learning_objective_ids']==x['task_design']['independent_subtargets'] for x in groups.values()),'拆分后目标引用一致')
check(all(x['generation_contract']['main_outcome']==x['outcome'] and x['generation_contract']['target_version']==m['version'] for x in goals.values()),'生成合同使用当前目标和版本')
check(all(not x['gse_alignment']['runtime_authority'] and not x['clb_alignment']['runtime_authority'] for x in groups.values()),'候选关系不被作为官方判级依据')
check(all(x['applicable_stages']==m['levels']['labels'] for x in groups.values() if x['kind']=='support_track'),'支持能力贯穿全部阶段')
check(all('unjudgeable' in x['assessment_check'] and x['learner_release_status']=='requires_reviewed_lesson' for x in goals.values()),'未审核课程不默认发布且可记不可判定')
check(all(set(x['new_ids'])<=goals.keys() for x in read('migration.json').values()),'旧目标ID迁移可解析')
for route in m['routes']:check(set(route['node_ids'])<=groups.keys(),'路线引用:'+route['id'])
for key,path in m['standard_reference_catalogs'].items():check((P/path).is_file(),'标准原始数据:'+key)
for n in groups.values():
    for r in n['gse_alignment']['candidate_objectives']:check((P/r['source_file']).is_file(),'候选PDF:'+r['objective_id'])
for r in read('official_oral_objectives.json'):
    check(10<=r['gse']<=90 and all((P/ref['file']).exists() for ref in r['source_refs']),'官方听说原文引用:'+r['id'])

rows=[json.loads(line) for line in (P/'vocabulary/gse_vocabulary.jsonl').read_text().splitlines()]
ids={r['itemId'] for r in rows}
check(len(rows)==len(ids)==v['server_total']==v['exported_total'],'词义JSONL总数、唯一ID、服务端总数一致')
with (P/'vocabulary/gse_vocabulary.csv').open(encoding='utf-8-sig',newline='') as f:
    csvrows=list(csv.DictReader(f))
check(len(csvrows)==len(rows) and {r['itemId'] for r in csvrows}==ids,'CSV词义完整性')
with sqlite3.connect(P/'vocabulary/gse_vocabulary.sqlite') as db:
    check(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','SQLite完整性')
    check(db.execute('SELECT count(*) FROM senses').fetchone()[0]==len(rows),'SQLite条目数量')
    check(db.execute("SELECT count(*) FROM senses WHERE gse_raw='N/A' AND gse IS NULL AND gse_status='ungraded'").fetchone()[0]==1357,'N/A不变成0分')
    check(db.execute("SELECT count(*) FROM senses WHERE gse_status='publisher_starred'").fetchone()[0]==540,'词义星号状态保留')
    check(db.execute("SELECT count(*) FROM search WHERE search MATCH 'book'").fetchone()[0]>0,'词义全文检索可用')
check(dict(collections.Counter(r['audience'] for r in rows))==v['by_audience'],'各人群数量一致')
check(all('definition' in r and 'expression' in r and 'example' in r and 'topics' in r for r in rows),'词义核心字段完整')
for name,sha in v['sha256'].items():check(hashlib.sha256((P/'vocabulary'/name).read_bytes()).hexdigest()==sha,'导出文件摘要:'+name)
raw_ids=set();raw_count=0
for band in v['bands']:
    for receipt in band['pages']:
        file=P/'vocabulary'/receipt['file'];raw=read('vocabulary/'+receipt['file'])
        check(hashlib.sha256(file.read_bytes()).hexdigest()==receipt['sha256'],'原始分页摘要:'+receipt['file'])
        check(len(raw['data'])==receipt['rows'] and raw['count']==band['server_count'],'原始分页数量:'+receipt['file'])
        raw_count+=len(raw['data']);raw_ids.update(r['itemId'] for r in raw['data'])
check(raw_count==len(rows) and raw_ids==ids,'原始响应到导出词义ID无遗漏')

# 用事实校验任务结果；语言是否自然、发音是否可理解仍需音频与人工锚点。
f=read('task_fixture.json')
intersection=set(f['learner_facts']['available'])&set(f['partner_private_facts']['available'])
check(intersection=={'16:30'},'改期任务确实可完成且解满足双方日程')
def valid_result(result):
    return result.get('time') in intersection and result.get('location')==f['partner_private_facts']['location']
check(valid_result({'time':'16:30','location':'library'}),'正确改期结果通过')
check(not valid_result({'time':'18:00','location':'library'}),'不满足对方日程的结果被拒绝')
check(not valid_result({'time':'16:30','location':'cafe'}),'地点错误的结果被拒绝')
check('model_answer' in f['allowed_support']['prohibited'] and 'sentence_completion' in f['allowed_support']['prohibited'],'独立检查禁完整答案和句型补全')
iv=f['independent_variant'];check(set(iv['learner_available'])&set(iv['partner_available'])=={'14:00'} and iv['partner_location']!='library','独立变体改变任务条件且可完成')
check(set(f['objective_ids'])<=goals.keys(),'具体任务引用当前目标')
check(not policy['public_ready'] and all(g['status']!='passed' for g in policy['mandatory_gates'] if g['id']!='MAP_DATA'),'未完成教学检查不误报全面上线')
for href in re.findall(r'href="([^"#]+)',(P/'report.html').read_text()):
    if href!='verification.json':check((P/href).exists(),'报告链接:'+href)

result={'status':'passed' if not errors else 'failed','errors':errors,'checks_run':len(checks),'counts':{'groups':len(groups),'objectives':len(goals),'official_oral_goals':len(read('official_oral_objectives.json')),'vocabulary':len(rows),'ungraded':1357,'starred':540},'scope':'数据结构、引用、词义导出完整性、发布规则和具体任务事实正反例；不覆盖语音和教学效果','public_ready':False,'remaining_gates':[g['id'] for g in policy['mandatory_gates'] if g['id']!='MAP_DATA']}
(P/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
if not errors:
    next(g for g in policy['mandatory_gates'] if g['id']=='MAP_DATA')['status']='passed'
    (P/'release_policy.json').write_text(json.dumps(policy,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
