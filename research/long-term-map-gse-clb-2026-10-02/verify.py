from pathlib import Path
import json,re,hashlib,collections
import fitz

P=Path(__file__).resolve().parent
def read(name):return json.loads((P/name).read_text())
def norm(s):return re.sub(r'[^a-z0-9]+',' ',s.lower()).strip()
m=read('curriculum_map.json');base=json.loads((P.parent/'long-term-map-2026-10-02/curriculum_map.json').read_text())
g=read('gse_objectives.json');grammar=read('gse_grammar.json');links=read('official_clb_gse_links.json');clb=read('clb_conditions.json')
errors=[]
def check(ok,msg):
 if not ok:errors.append(msg)
nodeids={n['id'] for n in m['nodes']};childids={c['id'] for c in m['subtargets']}
check(nodeids=={n['id'] for n in base['nodes']},'original node IDs differ')
check(len(nodeids)==len(m['nodes'])==140,'node uniqueness/count')
check(len(childids)==len(m['subtargets'])==420,'child uniqueness/count')
check(hashlib.sha256((P.parent/'long-term-map-2026-10-02/curriculum_map.json').read_bytes()).hexdigest()==m['source_map_sha256'],'source changed during build')
objectives={r['id']:r for r in g+grammar};official={r['id']:r for r in links};conditions={r['id']:r for r in clb}
check(len(objectives)==len(g+grammar),'objective IDs duplicate')
docs={};checked_refs=0
for r in g+grammar+links+clb:
 f=P/r['source_file']
 check(f.is_file(),f'missing {f}')
 if f.is_file():
  if str(f) not in docs:docs[str(f)]=fitz.open(f)
  check(1<=r['pdf_page']<=len(docs[str(f)]),f'page out of range {r["id"]}')
 check(10<=r.get('gse',10)<=90,f'GSE range {r["id"]}')
 checked_refs+=1
for n in m['nodes']:
 check(len(n['subtarget_ids'])==3 and set(n['subtarget_ids'])<=childids,f'children {n["id"]}')
 check(n['gse_alignment']['node_gse_score'] is None,f'invented score {n["id"]}')
 check(bool(n['task_blueprint']) and bool(n['task_design']),f'task fields {n["id"]}')
 for r in n['gse_alignment']['candidate_objectives']:
  o=objectives.get(r['objective_id']);check(bool(o),f'objective unresolved {n["id"]}')
  if o:check(o['gse']==r['gse'] and o['text']==r['text'],f'objective altered {n["id"]}')
  for oid in r['clb_official_links']:
   q=official.get(oid);check(bool(q),f'CLB unresolved {oid}')
   if q:check(q['gse']==r['gse'] and norm(q['gse_text'])==norm(r['text']),f'CLB score/text mismatch {oid}')
 for cid in n['clb_alignment']['condition_source_ids']:check(cid in conditions,f'condition unresolved {cid}')
for c in m['subtargets']:
 check(c['parent_id'] in nodeids,f'parent missing {c["id"]}')
 check(set(c['assessment_check'])=={'pass','partial','fail','unjudgeable'},f'assessment {c["id"]}')
 for r in c['gse_candidate_links']:check(r['objective_id'] in objectives,f'child objective {c["id"]}')
 check(c['generation_contract']['main_outcome']==c['outcome'],f'contract {c["id"]}')

# 校验原文抽取：删除 PDF 来源代码换行后，所有目标应仍存在于引用页。
def canonical(s):
 return norm(re.sub(r'(?m)^\s*(?:PRO|A)\s*$','',s))
text_errors=[]
for r in g:
 raw=docs[str(P/r['source_file'])][r['pdf_page']-1].get_text()
 if canonical(r['text']) not in canonical(raw):text_errors.append(r['id'])
check(not text_errors,'GSE text extraction mismatches: '+str(text_errors[:10]))

# 语法目标逐列词组应在原 PDF 同行词序中找到；忽略邻列表格插入。
grammar_errors=[]
for r in grammar:
 pg=docs[str(P/r['source_file'])][r['pdf_page']-1]
 ls=[]
 for block in pg.get_text('dict')['blocks']:
  for line in block.get('lines',[]):
   if 30<=line['bbox'][0]<180:ls.append((line['bbox'][1],''.join(s['text'] for s in line['spans'])))
 left=' '.join(t for y,t in sorted(ls))
 if norm(r['text']) not in norm(left):grammar_errors.append(r['id'])
check(not grammar_errors,'grammar text extraction mismatch: '+str(grammar_errors[:10]))

hrefs=re.findall(r'href="([^"#]+)(?:#[^"]*)?"',(P/'report.html').read_text())
for href in hrefs:
 if not href.startswith('http'):check((P/href).exists(),f'report link missing {href}')
check((P/'report.html').read_text().count('class="node"')==140,'report node count')
v={'status':'passed' if not errors else 'failed','errors':errors,'counts':{'nodes':len(nodeids),'subtargets':len(childids),'gse_objective_records_including_repeats':len(g),'grammar':len(grammar),'official_clb_gse_links':len(links),'clb_pages':len(clb),'source_records_checked':checked_refs},'gse_source_text_mismatches':text_errors,'grammar_text_check_requires_review':grammar_errors,'nodes_without_direct_gse':[n['id'] for n in m['nodes'] if not n['gse_alignment']['candidate_objectives']],'subtargets_without_gse_candidates':sum(not c['gse_candidate_links'] for c in m['subtargets']),'semantic_status':'对应关系为功能检索候选；未独立专家认证','source_pdf_sha256':{Path(k).name:hashlib.sha256(Path(k).read_bytes()).hexdigest() for k in docs},'limitations':['未用真人校准等级与评分','未对全部候选做逐条语义专家审核','未对HTML进行浏览器视觉检查','Toolkit词义级完整数据未导出']}
(P/'verification.json').write_text(json.dumps(v,ensure_ascii=False,indent=2))
print(json.dumps(v,ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
