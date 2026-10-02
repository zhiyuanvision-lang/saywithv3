"""按网页公开查询参数导出授权范围内GSE词义；可从已有页面恢复。"""
from pathlib import Path
import requests,json,time,math,hashlib,collections,csv,sqlite3,datetime
P=Path(__file__).resolve().parent/'vocabulary';RAW=P/'raw';RAW.mkdir(parents=True,exist_ok=True)
BASE='https://www.english.com/gse/teacher-toolkit/user/api/v1/vocabulary/'
S=requests.Session();AUDIENCES=['GL','YL','SSGL'];SIZE=1000
def fetch(lo,hi,page):
    path=RAW/f'band-{lo}-{hi}-page-{page}.json'
    params={'page':page,'size':SIZE,'sort':'expression.raw','query_string':'*','filters':json.dumps({'gseRange':{'from':str(lo),'to':str(hi)},'topics':[],'audiences':AUDIENCES,'grammaticalCategories':[]},separators=(',',':'))}
    if path.exists():return json.loads(path.read_text())
    for attempt in range(3):
        try:
            r=S.get(BASE+'search',params=params,timeout=40);r.raise_for_status();obj=r.json()
            assert isinstance(obj.get('data'),list) and isinstance(obj.get('count'),int)
            path.write_text(json.dumps(obj,ensure_ascii=False))
            return obj
        except Exception:
            if attempt==2:raise
            time.sleep(2*(attempt+1))
def collect(lo,hi,full=False):
    first=fetch(lo,hi,1);count=first['count']
    if not full and count>9000 and lo<hi:
        mid=(lo+hi)//2;return collect(lo,mid)+collect(mid+1,hi)
    rows=[];receipts=[]
    for page in range(1,math.ceil(count/SIZE)+1):
        try:o=first if page==1 else fetch(lo,hi,page)
        except requests.HTTPError:
            if lo==hi:raise
            print(f'接口返回错误，缩小分段 {lo}-{hi}',flush=True)
            mid=(lo+hi)//2;return collect(lo,mid)+collect(mid+1,hi)
        assert o['count']==count,('source count changed',lo,hi)
        rows.extend(o['data']);file=RAW/f'band-{lo}-{hi}-page-{page}.json'
        receipts.append({'page':page,'file':str(file.relative_to(P)),'rows':len(o['data']),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
        print(f'GSE {lo}-{hi}: page {page}, {len(rows)}/{count}',flush=True)
    assert len(rows)==count,('band missing',lo,hi,len(rows),count)
    bands.append({'from':lo,'to':hi,'server_count':count,'exported_rows':len(rows),'pages':receipts})
    return rows
bands=[]
total=fetch(10,90,1)['count'];rows=collect(10,90,full=True)
ids=[r['itemId'] for r in rows]
assert len(rows)==len(set(ids))==total,('full count mismatch',len(rows),len(set(ids)),total)
def score(r):
    import re
    m=re.match(r'^(\d+)',str(r.get('gse','')))
    return int(m.group(1)) if m else None
assert all(r['audience'] in AUDIENCES for r in rows)
rows.sort(key=lambda r:(r['expression'].lower(),r['audience'],score(r) or 0,r['itemId']))
(P/'gse_vocabulary.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
fields=['itemId','expression','definition','example','gse','cefr','audience','grammaticalCategories','collos','variants','topics','audioFiles','region','thesaurus']
with (P/'gse_vocabulary.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for r in rows:w.writerow({k:json.dumps(r.get(k),ensure_ascii=False) if isinstance(r.get(k),(dict,list)) else r.get(k,'') for k in fields})
db=P/'gse_vocabulary.sqlite'
if db.exists():db.unlink()
with sqlite3.connect(db) as c:
    c.execute('CREATE TABLE senses (id TEXT PRIMARY KEY, expression TEXT, definition TEXT, example TEXT, gse INTEGER, cefr TEXT, audience TEXT, raw_json TEXT)')
    c.executemany('INSERT INTO senses VALUES (?,?,?,?,?,?,?,?)',[(r['itemId'],r['expression'],r.get('definition',''),r.get('example',''),score(r),r.get('cefr',''),r['audience'],json.dumps(r,ensure_ascii=False)) for r in rows])
    c.execute('CREATE INDEX expression_idx ON senses(expression COLLATE NOCASE)');c.execute('CREATE INDEX level_idx ON senses(audience,gse)')
    c.execute('CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED,expression,definition,example)')
    c.execute('INSERT INTO search SELECT id,expression,definition,example FROM senses')
metadata={}
for name in ['topics','grammaticalCategories']:
    r=S.get(BASE+name,timeout=35);r.raise_for_status();(P/(name+'.json')).write_text(r.text);metadata[name]=len(r.json()['data'])
manifest={'status':'complete_for_public_toolkit_query_scope','retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'endpoint':BASE+'search','scope':{'audiences':AUDIENCES,'gse':[10,90],'query_string':'*','topics':[],'grammaticalCategories':[]},'server_total':total,'exported_total':len(rows),'unique_item_ids':len(set(ids)),'by_audience':dict(collections.Counter(r['audience'] for r in rows)),'bands':bands,'metadata_counts':metadata,'fields':fields,'authorization_assumption':'按用户要求视为已获得授权；没有绕过登录或访问限制','completeness_limit':'完整性针对当前网页接口返回的三类人群与10–90范围；不代表Pearson内部未发布的数据。音频只保存链接，未下载音频。','sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [P/'gse_vocabulary.jsonl',P/'gse_vocabulary.csv',db]}}
(P/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({k:manifest[k] for k in ['status','server_total','exported_total','unique_item_ids','by_audience']},ensure_ascii=False),flush=True)
