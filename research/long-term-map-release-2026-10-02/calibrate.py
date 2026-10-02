"""Coordinate-based source repair and conservative synthetic assessment checks."""
import json,re,pathlib,hashlib,collections,fitz
ROOT=pathlib.Path(__file__).resolve().parent
SRC=ROOT.parent/'long-term-map-gse-clb-2026-10-02'
def save(name,data):
 (ROOT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def normalize(t):return re.sub(r'[^a-z0-9]','',t.lower())
original=json.loads((SRC/'gse_objectives.json').read_text())
lookup=collections.defaultdict(list)
for r in original:lookup[(r['source'],r['pdf_page'],normalize(r['text']))].append(r)
corrected=[];changes=[];unresolved=[]
for source,filename in [('GSE.GENERAL','gse-adult-general.pdf'),('GSE.ACADEMIC','gse-learning-objectives-adult-academic-english.pdf'),('GSE.PROFESSIONAL','gse-learning-objectives-adult-professional-english.pdf')]:
 skill=None;score=None;band=None
 for pi,p in enumerate(fitz.open(SRC/'sources'/filename)):
  lines=[]
  for b in p.get_text('dict')['blocks']:
   for l in b.get('lines',[]):
    text=''.join(s['text'] for s in l['spans']).strip();lines.append((l['bbox'][1],l['bbox'][0],text))
  pending='';pending_skill=None;pending_score=None
  for y,x,text in sorted(lines):
   head=re.search(r'^GSE\s+.*?:\s*(Listening|Speaking|Reading|Writing)',text)
   if head:skill=head.group(1);band=text;score=None;continue
   if text in ['Listening','Speaking','Reading','Writing']:skill=text;score=None;continue
   if re.fullmatch(r'\d{2}',text) and 100<x<166 and 60<y<790:score=int(text);continue
   if x<160 or y>790:continue
   if text.startswith('Can '):pending=text;pending_skill=skill;pending_score=score
   elif pending:pending+=' '+text
   else:continue
   end=re.search(r'\(([A-Za-z][A-Za-z0-9]*)\)\s*$',pending)
   if not end:continue
   sentence=pending[:end.start()].strip();key=(source,pi+1,normalize(sentence))
   old=lookup.get(key,[])
   row={'id':old[0]['id'] if old else f'{source}.COORD.p{pi+1}.{len(corrected)+1}','source':source,'skill':pending_skill,'gse':pending_score,'source_band':band,'text':sentence,'origin_code':end.group(1),'pdf_page':pi+1,'source_file':'../long-term-map-gse-clb-2026-10-02/sources/'+filename,'extraction':'coordinate_order','source_verification':'page_text_and_row_geometry'}
   if pending_skill and pending_score and 10<=pending_score<=90:
    corrected.append(row)
    for prev in old:
     if prev['skill']!=pending_skill or prev['gse']!=pending_score:changes.append({'id':prev['id'],'before':{'skill':prev['skill'],'gse':prev['gse']},'after':{'skill':pending_skill,'gse':pending_score},'text':sentence})
   else:unresolved.append(row)
   pending=''
covered={r['id'] for r in corrected};missing=[r['id'] for r in original if r['id'] not in covered]
save('gse_objectives_corrected.json',corrected)
save('source_calibration_audit.json',{'original_rows':len(original),'coordinate_rows':len(corrected),'corrected_existing_rows':len(changes),'changes':changes,'original_rows_not_reconciled':missing,'unresolved_coordinate_rows':unresolved,'policy':'Only coordinate-extracted records may be used; unreconciled legacy references disabled. No CEFR proficiency calibration claimed.'})
# Rebuild oral catalog using corrected coordinate extraction, including all source references.
merged={}
for r in corrected:
 if r['skill'] not in ['Speaking','Listening']:continue
 key=(r['skill'],r['gse'],r['text']);id='GSE.'+hashlib.sha256('|'.join(map(str,key)).encode()).hexdigest()[:16]
 item=merged.setdefault(key,{'id':id,'outcome_en':r['text'],'skill':r['skill'],'gse':r['gse'],'audiences':[],'source_refs':[],'source_status':'coordinate_verified_published_objective','usage':'标准目标参考，不是用户测评分数','learner_release_status':'requires_reviewed_lesson'})
 audience=r['source'].split('.')[-1]
 if audience not in item['audiences']:item['audiences'].append(audience)
 item['source_refs'].append({'source_record_id':r['id'],'file':r['source_file'],'pdf_page':r['pdf_page']})
save('official_oral_objectives.json',sorted(merged.values(),key=lambda r:(r['gse'],r['skill'],r['outcome_en'])))
m=json.loads((ROOT/'curriculum_map.json').read_text());byid={r['id']:r for r in corrected}
contracts=[]
for obj in m['learning_objectives']:
 contracts.append({'objective_id':obj['id'],'outcome':obj['outcome'],'review_type':'automated_contract_review','semantic_alignment':'not_independently_validated','critical_meaning_policy':'生成器须将目标拆成可观察的信息/动作，每项绑定对话证据；允许正确改述','decision_order':['invalid_evidence -> unjudgeable','valid_critical_contradiction -> fail','missing_meaning_or_answer_support -> partial','all_required_meanings_and_task_conditions -> pass'],'fluency':'转写不支持口语流畅度或发音判断；没有音频时这些维度标不可判定','level':'阶段仅用于选课程难度，不能由一次任务通过推导CEFR/GSE成绩','publish_condition':'具体任务需完成信息约束、答案隔离、语音一致性和评分样例检查'})
 # A correction to source metadata cannot certify a semantic target relationship.
 for link in obj.get('gse_candidate_links',[]):
  ref=byid.get(link['objective_id']);link['source_metadata_status']='coordinate_verified' if ref else 'quarantined_unreconciled';link['runtime_authority']=False
 obj['calibration_contract_ref']='objective_calibration.json#'+obj['id']
save('objective_calibration.json',contracts)
m['standard_reference_catalogs']['gse_records']='gse_objectives_corrected.json'
m['standard_reference_catalogs'].pop('gse_objectives',None)
for group in m['capability_groups']:
 for link in group['gse_alignment']['candidate_objectives']:
  ref=byid.get(link['objective_id'])
  link['source_metadata_status']='coordinate_verified' if ref else 'quarantined_unreconciled'
  if ref: link['skill']=ref['skill'];link['gse']=ref['gse'];link['text']=ref['text']
  link['runtime_authority']=False
save('curriculum_map.json',m)
