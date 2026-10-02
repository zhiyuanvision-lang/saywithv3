from pathlib import Path
import json,re,hashlib,shutil,collections,csv,html
import fitz
from refinements import FACETS,SUPPORT,KEYWORDS,ANCHORS

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'long-term-map-2026-10-02'
SRC=ROOT/'sources'
def save(name,obj):
    (ROOT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2))
def norm(s):
    return re.sub(r'[^a-z0-9]+',' ',s.lower()).strip()
def matches(term,text):return bool(re.search(r'\b'+re.escape(term),text.lower()))
def pages(text):
    return [(int(p),t) for p,t in re.findall(r'=== PDF PAGE (\d+) ===(.*?)(?==== PDF PAGE|\Z)',text,re.S)]

COPIES={
 'gse-adult-general':ROOT.parent/'empower-feasibility-2026-10-01/gse/gse-learning-objectives-adult-general-english.pdf',
 'gse-grammar':ROOT.parent/'empower-feasibility-2026-10-01/gse/gse-grammar-guide-adult-framework.pdf',
 'clb-2012':ROOT.parent/'western-english-materials-2026-10-01/canada_clb/CLB_2012_full.pdf',
}
for name,p in COPIES.items():
    out=SRC/(name+'.pdf')
    if not out.exists():shutil.copy2(p,out)
    text='\n'.join(f'=== PDF PAGE {i+1} ===\n'+pg.get_text() for i,pg in enumerate(fitz.open(out)))
    (SRC/(name+'.txt')).write_text(text)

def parse_gse(name,file):
    rows=[]; mode=None; score=None; band=None
    for page,t in pages(file.read_text()):
        # PDFs list score once, then multiple objectives; carry score across pages.
        clean=[]
        for line in t.splitlines():
            line=line.strip()
            if line==str(page) or '© Pearson' in line:continue
            clean.append(line)
        text='\n'.join(clean)
        tokens=re.split(r'(?m)^(GSE [^\n]+|\d{2}|Reading|Listening|Speaking|Writing)$',text)
        for part in tokens:
            part=part.strip()
            if part in ['Reading','Listening','Speaking','Writing']:mode=part;continue
            if part.startswith('GSE '):
                mm=re.search(r':\s*(Reading|Listening|Speaking|Writing)',part)
                if mm:mode=mm.group(1);band=part
                else:mode=None
                continue
            if re.fullmatch(r'\d{2}',part):score=int(part);continue
            if mode and score and 10<=score<=90:
                for obj in re.findall(r'Can\s+.*?\([A-Za-z][A-Za-z0-9]*\)',part,re.S):
                    obj=re.sub(r'\n(?:PRO|A)\n','\n',obj)
                    obj=re.sub(r'\s+',' ',obj).strip()
                    code=re.search(r'\(([A-Za-z][A-Za-z0-9]*)\)$',obj).group(1)
                    sentence=re.sub(r'\s*\([A-Za-z][A-Za-z0-9]*\)$','',obj)
                    rows.append({'id':f'{name}.{mode}.{page}.{len(rows)+1}', 'source':name,'skill':mode,'gse':score,'source_band':band,'text':sentence,'origin_code':code,'pdf_page':page,'source_file':str(file.with_suffix('.pdf').relative_to(ROOT)),'score_status':'出版社条目分数；不是本App目标或用户的测评分数'})
    return rows

gse=[]
for name,f in [('GSE.GENERAL','gse-adult-general.txt'),('GSE.ACADEMIC','gse-learning-objectives-adult-academic-english.txt'),('GSE.PROFESSIONAL','gse-learning-objectives-adult-professional-english.txt')]:
    gse.extend(parse_gse(name,SRC/f))
save('gse_objectives.json',gse)

# 原文表格的出版社 CLB→GSE 对应，与我们节点→标准的候选关系分开保存。
official=[]
for f in sorted(SRC.glob('clb-stage-*-report.txt')):
    benchmark=None; skill=None
    for page,t in pages(f.read_text()):
        b=re.search(r'Stage [IVX]+\s*[–-]\s*Benchmark (\d+)',t)
        if b:benchmark=int(b.group(1))
        lines=t.splitlines()
        for line in lines:
            if line.strip() in ['Listening','Speaking','Reading','Writing']:skill=line.strip()
        if not benchmark or not skill or 'GSE Learning Objective' not in t:continue
        for m in re.finditer(r'(Can\s+.*?)[\n ]+(\d{2})(\*)?\s*\n((?:Below A1|A1|A2\+?|B1\+?|B2\+?|C1|C2)\s*\([^\n]+\))',t,re.S):
            sentence=re.sub(r'\s+',' ',m.group(1)).strip()
            # Table left-column text can fall between rows: only the final Can clause belongs to this row.
            sentence=sentence[sentence.rfind('Can '):]
            official.append({'id':f'CLB.GSE.{f.stem}.{page}.{len(official)+1}','clb':benchmark,'skill':skill,'gse':int(m.group(2)),'provisional':bool(m.group(3)),'cefr_as_published':m.group(4),'gse_text':sentence,'pdf_page':page,'source_file':str(f.with_suffix('.pdf').relative_to(ROOT)),'relation':'Pearson 2024 官方发布的条目对应；不代表本App节点获官方认证'})
save('official_clb_gse_links.json',official)

clb=[]
for page,t in pages((SRC/'clb-2012.txt').read_text()):
    m=re.search(r'(Listening|Speaking)\s*[–-]\s*Benchmark\s+(\d+)',t)
    if not m:continue
    clb.append({'id':f'CLB.{m.group(1)}.{m.group(2)}.p{page}','skill':m.group(1),'benchmark':int(m.group(2)),'pdf_page':page,'printed_page':page-26,'source_file':'sources/clb-2012.pdf','text':t.strip(),'profile':t.split('Profile of Ability',1)[1].strip() if 'Profile of Ability' in t else None,'status':'逐页原文；包含能力陈述、表现指标及样例，子栏目尚未结构化'})
save('clb_conditions.json',clb)

# 语法指南用列坐标提取，避免把邻列的例句、分数拼进目标正文。
grammar=[]
for pi,p in enumerate(fitz.open(SRC/'gse-grammar.pdf')):
    words=p.get_text('words')
    lines=[]
    for block in p.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            lines.append((line['bbox'][0],line['bbox'][1],''.join(s['text'] for s in line['spans'])))
    scores=[]
    for w in words:
        if 680<w[0]<790 and re.fullmatch(r'\d{2}',w[4]) and 10<=int(w[4])<=90:
            scores.append((w[1],int(w[4])))
    scores.sort()
    for i,(y,score) in enumerate(scores):
        end=scores[i+1][0]-1 if i+1<len(scores) else p.rect.height-30
        vals=[]
        for x1,x2 in [(30,180),(180,330),(330,510),(510,680)]:
            selected=sorted((yy,t) for xx,yy,t in lines if x1<=xx<x2 and y-2<=yy<end)
            # 中途分级标题或重复表头不属于上一行目标。
            texts=[]
            for yy,t in selected:
                if t.strip() in ['Learning Objective','Structure','Example','Grammatical Categories','GSE'] or re.match(r'^(?:A[12]|B[12]|C[12])\b',t.strip()):break
                texts.append(t)
            vals.append(re.sub(r'\s+',' ',' '.join(texts)).strip())
        if not vals[0].startswith('Can '):continue
        grammar.append({'id':f'GSE.GRAMMAR.p{pi+1}.{i+1}','gse':score,'text':vals[0],'structure':vals[1],'examples':vals[2],'categories':vals[3],'pdf_page':pi+1,'source_file':'sources/gse-grammar.pdf'})
save('gse_grammar.json',grammar)

LEVELS={'Pre-A1':(10,21),'A1':(22,29),'A2':(30,42),'B1':(43,58),'B2':(59,75),'C1':(76,84),'C2':(85,90)}
CLB_BANDS={1:(10,19),2:(20,27),3:(28,34),4:(35,41),5:(42,46),6:(47,52),7:(53,58),8:(59,66),9:(67,72),10:(73,78),11:(79,84),12:(85,90)}
# 按原节点明确的沟通目的选择词面；保留跨等级条目以暴露原地图的等级争议。
OVERRIDES={
'CONTACT.Pre-A1':['greet','farewell'], 'CONTACT.A1':['introduce themselves','name'],
'REQUEST.A2':['invitation','invite','refuse requests','suggestions','excuses'],
'ARRANGE.A2':['arrangements','schedule','meet','confirm information','excuses'],
'SERVICE.A2':['reservation','price','directions','goods and services'],
'INFO.Pre-A1':['name','number'], 'INFO.A1':['time','date','phone number','personal details'],
'STORY.A2':['past','plans','future'], 'PHONE.A2':['appointment','phone messages','reservation'],
'MEDIA.A1':['announcement','recorded message'],
'SOUND.CONTRAST':['phonological','pronunciation','articulation'],
'FORM.QUESTION':['question'], 'FORM.TIME':['past','present','future'],
'FORM.NEGATION':['negative','negation'], 'FORM.CLAUSE':['subject','clause','construction'],
'FORM.CONDITION':['conditional','condition','possibility','modal'],
'FORM.QUANTITY':['quantity','quantities','comparison','comparative','quantifier'],
'FORM.SPACE':['place','direction','preposition'],
}
DIRECT={
 'CONTACT.A1':['Can ask someone for their name.'],
 'INFO.Pre-A1':['Can understand cardinal numbers from 1 to 20.'],
 'STORY.A2':['Can describe very basic events in the past using simple linking words'],
 'ARRANGE.A2':['Can make excuses using basic fixed expressions.','Can confirm information using some simple fixed expressions.'],
 'SERVICE.A2':['Can make a hotel, restaurant, or transportation reservation on the phone.','Can ask basic questions about colour, size, price','Can ask for simple directions from X to Y'],
 'REQUEST.A2':['Can make simple invitations using basic fixed expressions.','Can refuse requests politely, using simple language.','Can make and respond to suggestions.'],
}
SEEDS={
 'CONTACT':{'context':'认识一位新同学或新同事','facts':['双方参加同一活动','各自有一个兴趣和一个近期经历'],'role_rule':'对方回应后留出接话机会；不替用户提出问题或介绍自己'},
 'INFO':{'context':'核对一次活动的安排','facts':['地点有旧版与新版信息','日期、时间、人数分别由不同角色掌握'],'role_rule':'只回答用户已提出的问题；矛盾信息需用户发现并核查'},
 'DESCRIBE':{'context':'向未见过现场的人介绍地点、人物或变化','facts':['提供必要照片或事实卡','听者有一个具体关注点'],'role_rule':'根据实际描述追问；不给用户完整描述'},
 'NEEDS':{'context':'向同伴说明偏好、感受和需要','facts':['提供几个可选活动','用户可使用自己真实的偏好'],'role_rule':'不替用户决定感受；根据已表达的内容回应'},
 'STORY':{'context':'讲述一次经历并回应听者','facts':['可使用真实经历或提供事件卡','事实卡含背景、先后和转折'],'role_rule':'针对已述内容追问；不把事件背景知识纳入语言分数'},
 'EXPLAIN':{'context':'向另一人解释一个已知过程或问题','facts':['提供步骤、现象和已知原因','未知原因明确标为未知'],'role_rule':'按听者背景请求澄清，不凭专业知识判语言能力'},
 'REQUEST':{'context':'邀请同伴参加活动或请求协助','facts':['活动、时间或帮助内容已知','对方可接受、拒绝或提出限制'],'role_rule':'按隐藏限制回应；保留接受、拒绝和替代的自然路径'},
 'ARRANGE':{'context':'双方商定共同活动','facts':['用户可用时间16:30或18:00','对方可用时间15:00或16:30','对方只能在图书馆见面'],'role_rule':'日程只在交谈中透露；不给最终答案'},
 'SERVICE':{'context':'办理服务或解决服务问题','facts':['提供商品、价格、预订日期或路线卡','复杂任务另提供条款与服务记录'],'role_rule':'根据所选子目标只提供相关服务信息；未询问的关键条件不主动全部列出'},
 'COMPARE':{'context':'比较两到三个活动或服务选项','facts':['各选项具有价格、位置和限制','提供证据来源及其已知局限'],'role_rule':'允许不同选择，只检查比较依据和结论的语言表达'},
 'OPINION':{'context':'讨论熟悉议题或给定复杂议题','facts':['提供必要背景事实和不同立场','观点可以由用户自行选择'],'role_rule':'追问理由或提出相关反对意见；不按立场对错评分'},
 'RELATE':{'context':'回应帮助、拒绝提议或讨论一次分歧','facts':['明确双方关系和已发生事件','允许用户选择自己的边界'],'role_rule':'不按对方满意度评分；核查表达意图是否清楚适切'},
 'COLLAB':{'context':'共同筹办一个活动','facts':['各角色掌握不同任务和进度','明确预算、时间和待办事项'],'role_rule':'按轮次贡献信息；不替用户总结和确认职责'},
 'REPAIR':{'context':'解决一次真实的理解障碍','facts':['设置日期、指代或条件的歧义','保存歧义的正确解释'],'role_rule':'用户定位障碍后按规则解释；不能随机制造无限误解'},
 'LISTEN':{'context':'听取对方信息后作出回应或行动','facts':['音频含必要信息和一个相关变式','提供可判断的正确行动'],'role_rule':'回应语言负担不超过已知资源；音频与转写必须一致'},
 'MEDIA':{'context':'听公告、留言、访谈或节目摘录','facts':['保存输入文本、说话者和目的','按子目标标记关键时间、观点或隐含态度'],'role_rule':'不用生成者自己的标签作为唯一评分证据'},
 'PHONE':{'context':'通过电话预约、留言或协调事项','facts':['提供双方身份与来电目的','日程或任务信息由不同角色掌握'],'role_rule':'仅有声音；允许合理澄清，不能泄露完整答案'},
 'MEDIATE':{'context':'把甲的信息转述给乙并帮助理解','facts':['保存甲的原意和关键限定','明确乙需要知道什么'],'role_rule':'区分来源和用户意见；允许改述，不要求逐字复现'},
}
DIFFICULTY={
 'Pre-A1':{'topic':'熟悉且具体','input':'短语或简短问句，清晰慢速','output':'词或固定短语','partner':'熟悉、耐心、可重复','complication':'一个直接需求'},
 'A1':{'topic':'个人信息和即时需求','input':'简短问句和指令，清晰慢速','output':'简单句和短回应','partner':'合作，可应请求重复','complication':'少量具体信息'},
 'A2':{'topic':'熟悉的日常事项','input':'短对话，清晰，可含常见变式','output':'简短连接表达与相互回应','partner':'可合理澄清，独立检查不供答案','complication':'一个冲突、限制或信息变化'},
 'B1':{'topic':'熟悉领域及常见意外','input':'连贯交流，清晰自然，含必要细节','output':'连接叙述、解释和追问','partner':'要求用户主动补信息','complication':'多个相关信息或限制'},
 'B2':{'topic':'较广话题，提供必要背景','input':'较长输入或多人不同观点','output':'持续互动、组织论点与回应','partner':'有不同意见，正常交接轮次','complication':'权衡、理由和条件'},
 'C1':{'topic':'复杂或抽象议题，提供知识背景','input':'较长且可能有隐含态度的自然输入','output':'灵活组织、精确限定、调节语体','partner':'多角色关系与立场','complication':'隐含条件、复杂分歧或结构'},
 'C2':{'topic':'复杂且有细微意义的议题','input':'快速复杂互动，含修辞与细微限定','output':'精确重构意义、立场和语气','partner':'多方观点，允许合理澄清','complication':'微妙立场与隐含关系'},
}
AREA={
'CONTACT':['I'],'RELATE':['I'],'NEEDS':['I','IV'],'REQUEST':['I','III'],
'ARRANGE':['III','IV'],'SERVICE':['III','II'],'EXPLAIN':['II','IV'],
'INFO':['IV','II'],'DESCRIBE':['IV'],'STORY':['IV'],'COMPARE':['III','IV'],
'OPINION':['IV'],'COLLAB':['I','IV'],'REPAIR':['I','IV'],
'LISTEN':['I','IV'],'MEDIA':['IV'],'PHONE':['I','III'],'MEDIATE':['IV']}

RESOURCE={
'CONTACT':('姓名、身份、兴趣、话题衔接','问候；介绍；接话；结束交谈','问句、代词、基本陈述'),
'INFO':('时间、日期、数字、地点、联系方式、信息来源','询问；提供；核对；限定','问句、数量、指代、否定'),
'DESCRIBE':('属性、位置、习惯、变化、感官细节','描述；举例；突出重点','形容词、频率、比较、关系从句'),
'NEEDS':('偏好、需求、情绪、程度','表达需要；给出理由；核查理解','否定、原因、程度与情态'),
'STORY':('事件、时间、顺序、转折','交代背景；叙述；解释后果','时态、时间连接、因果连接'),
'EXPLAIN':('步骤、现象、原因、条件、例外','说明过程；解释问题；确认理解','祈使、顺序、因果、条件'),
'REQUEST':('活动、帮助、许可、负担','请求；邀请；接受；婉拒；替代','情态、问句、否定与原因'),
'ARRANGE':('日程、时间冲突、限制、方案、职责','提出安排；说明冲突；替代；确认','时间、否定、建议、条件与比较'),
'SERVICE':('商品、数量、费用、预订、路线、条款','说明需求；询价；确认；投诉；协商','数量、问句、否定、时态与条件'),
'COMPARE':('属性、标准、选择、证据、风险','比较；推荐；权衡；限定','比较级、对比连接、条件与程度'),
'OPINION':('观点、理由、例子、证据、反对意见','表态；论证；回应；限定','因果、让步、情态与限定'),
'RELATE':('感谢、道歉、关心、分歧、边界','回应关系；婉拒；反馈；修复','情态、否定、缓和与原因'),
'COLLAB':('任务、进度、贡献、行动事项','接话；汇报；澄清；总结','时态、问句、指代和连接'),
'REPAIR':('不理解、指代、条件、缺词','重复；澄清；改述；核对','问句、否定、指代与限定'),
'LISTEN':('关键信息、意图、否定、条件、态度','识别；提取；按信息行动','接收端识别问句、否定、时间、条件'),
'MEDIA':('公告、留言、访谈、节目、立场','抓主旨；提取细节；区分观点','接收端识别时间、连接、限定'),
'PHONE':('通话身份、目的、预约、留言、故障','开场；说明目的；澄清；确认；结束','问句、时间、否定与条件'),
'MEDIATE':('来源、关键事实、他人立场、分歧','提取；概括；改述；核查','指代、转述、连接与限定'),
}

mapdata=json.loads((BASE/'curriculum_map.json').read_text())
import os
for source in mapdata['sources'].values():
    if source.get('file'):
        original=(BASE/source['file']).resolve()
        source['file']=os.path.relpath(original,ROOT)
mapdata['sources']['GSE']['file']='sources/gse-adult-general.pdf'
mapdata['sources']['CLB']['file']='sources/clb-2012.pdf'
mapdata['sources']['CLB_GSE_2024']={'title':'Pearson Alignment of CLB to GSE, November 2024, Stages I–III','file':'sources/clb-stage-I-report.pdf','relation':'官方条目对应报告；本App节点对应仍需核查'}
positions=collections.Counter();children=[];summary=[]
byphrase=collections.defaultdict(list)
for r in official:byphrase[norm(r['gse_text'])].append(r)
def select(n):
    family=n['family_id']; words=n.get('_anchor_terms',OVERRIDES.get(n['id'],KEYWORDS.get(family,KEYWORDS.get(family.split('.')[0],[]))))
    lo,hi=LEVELS.get(n['level_candidate'],(10,90));wanted='Listening' if family in ['LISTEN','MEDIA'] else 'Speaking'
    pool=grammar if n['id'].startswith('FORM.') else [r for r in gse if r['skill']==wanted]
    ranked=[]
    for r in pool:
        text=r['text'].lower(); matched=[w for w in words if matches(w,text)]
        if not matched:continue
        dist=max(lo-r['gse'],r['gse']-hi,0)
        if dist>5:continue
        rank=sum(2+min(len(w)/12,2) for w in matched)-dist*1.2+(.4 if r.get('source')=='GSE.GENERAL' else 0)
        ranked.append((rank,r,matched))
    ranked.sort(key=lambda x:(-x[0],x[1]['gse'],x[1]['id']))
    # 优先让不同功能词各有参考，避免六条全部落在同一子功能。
    diverse=[]
    for word in words:
        for item in ranked:
            if word in item[2] and item not in diverse:diverse.append(item);break
    ranked=diverse+ranked
    picked=[];seen=set()
    for rank,r,matched in ranked:
        key=(norm(r['text']),r['gse'])
        if key in seen:continue
        seen.add(key)
        link={'objective_id':r['id'],'text':r['text'],'gse':r['gse'],'skill':r.get('skill','Grammar'),'pdf_page':r['pdf_page'],'source_file':r['source_file'],'matched_terms':matched,'relation':'功能相关候选；需要核查范围、条件与本节点子目标是否匹配','official_node_equivalence':False,'level_conflict':not lo<=r['gse']<=hi,'clb_official_links':[q['id'] for q in byphrase[norm(r['text'])] if q['gse']==r['gse']]}
        picked.append(link)
        if len(picked)>=6:break
    for phrase in DIRECT.get(n['id'],[]):
        found=next((r for r in gse if r['text'].startswith(phrase) and r['source']=='GSE.GENERAL'),None)
        if found and all(r['objective_id']!=found['id'] for r in picked):
            picked.append({'objective_id':found['id'],'text':found['text'],'gse':found['gse'],'skill':found['skill'],'pdf_page':found['pdf_page'],'source_file':found['source_file'],'matched_terms':[phrase],'relation':'原文功能核对后补入；本节点完整范围仍非官方等价','official_node_equivalence':False,'level_conflict':not lo<=found['gse']<=hi,'clb_official_links':[q['id'] for q in byphrase[norm(found['text'])] if q['gse']==found['gse']]})
    return picked

for n in mapdata['nodes']:
    family=n['family_id'];nodeid=n['id'];level=n['level_candidate']
    if n['type']=='communication':
        pos=positions[family]
        parts=FACETS[family].splitlines()[pos].split('|')
        n['_anchor_terms']=ANCHORS[family].splitlines()[pos].split(';')
        if level=='C2' and family in ['CONTACT','INFO','DESCRIBE','NEEDS','STORY','REQUEST','COMPARE','RELATE','MEDIATE']:
            n['_anchor_terms'].append('finer shades of meaning')
        positions[family]+=1
    else:parts=SUPPORT[nodeid].split('|')
    n['subtarget_ids']=[]
    for i,label in enumerate(parts,1):
        cid=f'{nodeid}.s{i}';n['subtarget_ids'].append(cid)
        children.append({'id':cid,'parent_id':nodeid,'outcome':label,'cefr_candidate':level,'origin':'本App原创子目标，非GSE或CLB原文翻译','assessment_check':{'pass':f'在父目标规定的条件下，独立完成“{label}”，关键意义清楚且未反转','partial':'需要额外提示，或关键信息部分缺失；记录具体帮助与缺失','fail':'在信息、识别和背景均有效时，无法完成或关键意义错误','unjudgeable':'录音识别不可靠、任务缺少必要信息或对方替用户完成目标'},'mastery_policy':'记录每个子目标的证据；父目标不因一个子目标成功而整体掌握；数值阈值待试点','gse_mapping_status':'继承父节点的候选池；生成前须选择与此子目标匹配的条目，不可自动视为全部对应'})
    # 发音、学习过程支持目标不强行对应通用沟通Can-do条目。
    indirect=n['id'].startswith('SOUND.') or n['id'] in ['LEX.RETRIEVE','LEX.ACQUIRE','STRATEGY.PLAN','STRATEGY.MONITOR']
    refs=[] if indirect else select(n)
    n.pop('_anchor_terms',None)
    n['gse_alignment']={'node_gse_score':None,'candidate_objectives':refs,'status':'已提取出版社原文与分数；节点对应为检索和功能分析候选，未获专家校准','policy':'不能将候选分数平均为节点或用户分数；不能按GSE分数强制串行教学'}
    official_ids=list(dict.fromkeys(q for r in refs for q in r['clb_official_links']))
    chosen=[r for r in official if r['id'] in official_ids]
    skill='Listening' if family in ['LISTEN','MEDIA'] else 'Speaking'
    benches=sorted(set(r['clb'] for r in chosen if r['skill']==skill))
    kind='经候选GSE条目连接出版社CLB对照；对本App节点仍是候选'
    if not benches:
        lo,hi=LEVELS.get(level,(10,90));benches=[b for b,(a,z) in CLB_BANDS.items() if a<=hi and z>=lo]
        kind='只作检索定位：按出版社范围选择条件参考，不构成节点等级等价'
    n['clb_alignment']={'candidate_benchmarks':benches,'skill':skill,'competency_area_candidates':AREA.get(family,['I','II','III','IV']),'official_link_ids':official_ids,'condition_source_ids':[r['id'] for r in clb if r['benchmark'] in benches and r['skill']==skill],'relation':kind,'official_node_equivalence':False}
    if n['type']!='communication':
        n['clb_alignment']['knowledge_strategy_reference']={'source_file':'sources/clb-2012.pdf','pdf_pages':[65,77,89],'relation':'CLB各阶段口语知识与策略原文；支持能力不等价于某个CLB沟通任务'}
        n['gse_alignment']['status']='支持目标优先参考GSE语法或CLB知识策略；不存在直接条目时明确保留缺口，不用重复/描述等无关条目替代'
    n['task_design']={
      'primary_target_policy':'一次教学/测评明确一个主目标；其他节点作为支持观察，分别保存证据',
      'independent_subtargets':n['subtarget_ids'],
      'difficulty_axes':['话题熟悉度','输入长度和信息密度','表达组织要求','对方支持量','参与人数与轮次','意外情况','语体关系','声音清晰度与说话者变化'],
      'condition_policy':'读取引用的CLB原文表现条件，按沟通子目标选择；时间/轮次仅为任务参数，不作为官方等级阈值',
      'required_script_fields':['双方角色与信息','本次主子目标','关键意义及可接受结果','隐藏信息和对方回应规则','难度各轴的具体值','允许帮助','评分证据与识别可信度','独立测评变体','延迟检查'],
      'variants':{'supported':'提供已知词与必要背景，表达提示渐退','independent':'隐藏完整答案；保留任务本身允许的澄清','transfer':'改变至少一个影响任务的条件；不仅替换名字','retention':'隔期无完整答案再完成；间隔随证据调整'},
      'dependencies_policy':'原recommended_before仅为建议；支持点按失败证据触发'}
    n['task_blueprint']={'seed':SEEDS.get(family,{'context':'嵌入当前沟通任务练习本支持目标','facts':['沿用主沟通目标的背景事实'],'role_rule':'记录支持目标表现，不能只按任务最终结果推断支持能力'}),'primary_subtarget_rule':'从independent_subtargets中选择本次重点；覆盖其他子目标需另存证据','difficulty':DIFFICULTY.get(level,DIFFICULTY['B1']),'difficulty_status':'App原创任务设计起点；参考CLB引用条件，非标准逐字规定，需校准','acceptable_results':n['success_criterion'],'independent_check':'使用相同能力要求的新事实和隐藏信息；不用原练习的完整答案','measurement':'依据实际音频、互动时序及关键意义，分别记录各子目标与支持量'}
    resource=RESOURCE.get(family,('以实际沟通任务为载体选择词义与声音','围绕支持子目标设计表达','根据支持目标选择必要结构'))
    n['language_resources']={'vocabulary_domains':resource[0],'expression_functions':resource[1],'grammar_domains':resource[2],'official_grammar_candidates':[r['objective_id'] for r in refs if r['skill']=='Grammar'],'original_expression_examples':n.get('example_expressions',[]),'policy':'每课以已知词句为基础，仅补当前目标必要的未知资源；支持多种正确说法','vocabulary_level_status':'主题与示例为原创候选；未获得完整GSE词义级数据导出，不编造词汇分数'}
    summary.append({'id':nodeid,'label':n['label'],'cefr':level,'subtargets':len(parts),'gse_candidates':len(refs),'clb_links':len(official_ids),'clb_conditions':len(n['clb_alignment']['condition_source_ids']),'cross_level_candidates':sum(r['level_conflict'] for r in refs)})

CONCEPTS={
 '问候':['greet'],'告别':['farewell','leave-taking'],'姓名':['name'],'身份':['introduc'],
 '兴趣':['interest','hobbies'],'开场':['start','initiate'],'接话':['turn','conversation'],
 '结束':['close','end'],'数字':['number'],'时间':['time','schedule','arrange'],'地点':['place','location'],
 '联系方式':['phone number','personal details'],'日程':['schedule','arrange'],'路线':['direction'],
 '数量':['quantity','quantities','amount','number'],'核对':['check','confirm','clarif'],
 '核查':['check','confirm','clarif'],'追问':['question','clarif'],'来源':['source','information'],
 '限定':['qualif','precision','modification','shades'],'例外':['exception','modification'],
 '人物':['people','appearance','person'],'物品':['object','product'],'位置':['position','place'],
 '属性':['characteristic','object'],'习惯':['habit','routine'],'频率':['frequency','how often'],
 '变化':['change','reaction'],'感受':['feel','emotion'],'情绪':['feel','emotion'],
 '偏好':['prefer','like'],'需求':['need','request'],'需要':['need','request'],
 '理由':['reason'],'原因':['reason','cause'],'经历':['experience','story','narrat'],
 '过去':['past'],'未来':['future','plan'],'顺序':['sequence','order','link'],
 '转折':['story','narrat','plot'],'视角':['narrat','shades'],'修辞':['rhetoric','shades'],
 '用途':['used for'],'步骤':['instruction','process','procedure'],
 '问题':['problem'],'故障':['problem','technical'],'处理办法':['solution'],
 '请求':['request','permission'],'邀请':['invit'],'拒绝':['refus','declin'],'接受':['accept','agree'],
 '替代':['suggest','alternative','arrangement'],'不方便':['excuse'],'安排':['arrange','schedule','plan'],
 '冲突':['conflict','negotiat'],'方案':['alternative','proposal','plan'],'取舍':['negotiat','advantage'],
 '诉求':['request','complaint'],'预订':['reservation'],'价格':['price'],'费用':['price','cost'],
 '商品':['goods','shop','purchase'],'条款':['contract','term'],'责任':['responsib'],
 '比较':['compar'],'推荐':['recommend','choice'],'风险':['risk','disadvantage'],
 '证据':['evidence','argument'],'观点':['opinion','point of view'],'论点':['argument'],
 '反对':['counter','disagree'],'例子':['example','illustrate'],'感谢':['thank','polite'],
 '道歉':['apolog'],'祝贺':['congratulat'],'关心':['sympathy','feel'],'边界':['disagree','criticism'],
 '反馈':['feedback','critic'],'误会':['misunderstand'],'任务':['task'],'进度':['progress'],
 '轮次':['turn'],'发言':['turn','contribution'],'总结':['summaris','summariz','conclusion'],
 '澄清':['clarif'],'重复':['repeat','repetition'],'放慢':['slow'],'拼写':['spell'],
 '缺词':['word','vocab','circumlocution'],'改述':['paraphras','reformulat','rephras'],
 '主旨':['main point','main idea'],'细节':['detail','specific','factual'],
 '否定':['negat','can’t'],'语体':['register','style'],'态度':['attitude','feeling','shades'],
 '公告':['announcement'],'留言':['message'],'通话':['phone','call'],'预约':['appointment','reservation'],
 '转告':['pass on','relay','message'],'转述':['paraphras','summaris','message'],
 '指代':['pronoun','reference'],'意义':['meaning','shades'],'语气':['polite','intonation','shades'],
 '介绍':['introduc'],'交谈':['conversation'],'话题':['topic','conversation'],'问一个':['question'],
 '环境':['environment','home','place'],'喜欢':['like','prefer'],'想要':['want','needs'],'体验':['experience'],
 '事件':['event','narrat'],'背景':['background','narrat'],'过程':['process','procedure'],
 '条件':['condition','qualif'],'礼貌':['polite'],'敏感':['sensitive','controversial'],
 '回应':['respond','react'],'听者':['audience','listener'],'细微':['finer shades'],
 '论证':['argument'],'分歧':['disagree','conflict'],'倾听':['listen'],
 '意图':['intent','purpose'],'理解':['understand','clarif'],'意愿':['invit','offer'],
}
nodemap={n['id']:n for n in mapdata['nodes']}
for c in children:
    parent=nodemap[c['parent_id']]
    terms=list(dict.fromkeys(t for zh,en in CONCEPTS.items() if zh in c['outcome'] for t in en))
    candidates=[]
    for r in parent['gse_alignment']['candidate_objectives']:
        mt=[t for t in terms if matches(t,r['text'])]
        if mt:candidates.append({'objective_id':r['objective_id'],'matched_concepts':mt,'relation':'子目标功能检索候选，非完整等价；需逐条核查条件'})
    # 父候选池不足时检索全文，仍只输出可追溯的候选，不自动继承掌握。
    if len(candidates)<2 and not (c['parent_id'].startswith('SOUND.') or c['parent_id'] in ['LEX.RETRIEVE','LEX.ACQUIRE','STRATEGY.PLAN','STRATEGY.MONITOR']):
        lo,hi=LEVELS.get(c['cefr_candidate'],(10,90))
        wanted='Listening' if parent['family_id'] in ['LISTEN','MEDIA'] or c['outcome'].startswith(('听','识别慢速','识别所问')) else 'Speaking'
        pool=grammar if c['parent_id'].startswith('FORM.') else [r for r in gse if r['skill']==wanted]
        ranked=[]
        for r in pool:
            mt=[t for t in terms if matches(t,r['text'])]
            dist=max(lo-r['gse'],r['gse']-hi,0)
            if not mt or dist>5:continue
            ranked.append((len(mt)*3-dist,r,mt))
        ranked.sort(key=lambda x:(-x[0],x[1]['gse'],x[1]['id']))
        seen={r['objective_id'] for r in candidates};seen_text=set()
        for score,r,mt in ranked:
            if r['id'] in seen or norm(r['text']) in seen_text:continue
            seen.add(r['id']);seen_text.add(norm(r['text']))
            candidates.append({'objective_id':r['id'],'matched_concepts':mt,'relation':'子目标全文功能检索候选，可能仅覆盖表达资源的一部分；待语义核查'})
            if len(candidates)>=3:break
    c['gse_candidate_links']=candidates
    c['gse_mapping_status']='已给出子目标候选关系，待语义核查' if candidates else '暂无可靠直接对应；使用原创目标与CEFR/CLB参考，禁止模型编造GSE条目或分数'
    c['clb_condition_source_ids']=parent['clb_alignment']['condition_source_ids']
    c['generation_contract']={'main_outcome':c['outcome'],'target_version':'0.3-gse-clb-draft','source_selection':'从此子目标的候选关系核查后选择原文条目；候选未核查时只按原创目标生成','task_blueprint_parent':parent['id'],'assessment_check':c['assessment_check'],'must_preserve':['关键意义','任务条件','隐藏信息','允许支持','独立检查不泄露答案'],'must_vary':['事实内容','角色背景','至少一个影响任务的条件'],'quality_checks':['目标确实需要用户表达','双方限制一致且任务可完成','词句自然','输入与目标难度一致','角色不替用户完成关键动作','评分支持正确改述'],'fallback':'质检失败时回退同子目标审核模板；没有审核模板则标待审核，不能假定已有回退资源'}

mapdata['version']='0.3-gse-clb-draft'
mapdata['source_map_sha256']=hashlib.sha256((BASE/'curriculum_map.json').read_bytes()).hexdigest()
mapdata['source_map']='../long-term-map-2026-10-02/curriculum_map.json'
mapdata['subtargets']=children
mapdata['authorization_assumption']='依用户指示，按授权已通过开展本地补充；此字段不表示已核查授权文件'
mapdata['alignment_policy']='CEFR保留阶段；GSE原文条目及分数用于细化候选；CLB原文与Pearson 2024对照用于条件参考。原创节点未经官方等价认证。'
save('curriculum_map.json',mapdata)
save('node_alignment_audit.json',summary)
save('standard_ranges.json',{'gse_cefr':LEVELS,'clb_gse_pearson_2024':CLB_BANDS,'source':'sources/clb-stage-I-report.pdf#page=6','warning':'参考范围不是单一任务/用户成绩自动转换公式'})
with (ROOT/'subtargets.csv').open('w') as f:
    w=csv.writer(f);w.writerow(['id','parent_id','cefr_candidate','outcome'])
    for c in children:w.writerow([c['id'],c['parent_id'],c['cefr_candidate'],c['outcome']])

# 逐节点可阅读报告；固定原文引用、候选关系与原创子目标的边界。
esc=html.escape
cards=[]
for n in mapdata['nodes']:
    cs=[c for c in children if c['parent_id']==n['id']]
    lis=''.join('<li>'+esc(c['outcome'])+'</li>' for c in cs)
    rs=''.join(f'<tr><td>{esc(r["text"])}</td><td>{r["gse"]}</td><td>{esc(r["skill"])}</td><td><a href="{r["source_file"]}#page={r["pdf_page"]}">PDF {r["pdf_page"]}</a></td><td>{"跨原等级，需核对" if r["level_conflict"] else "功能相关候选"}</td></tr>' for r in n['gse_alignment']['candidate_objectives'])
    conditions=''.join(f'<li><a href="{r["source_file"]}#page={r["pdf_page"]}">{r["skill"]} CLB {r["benchmark"]} · PDF {r["pdf_page"]}</a></li>' for r in clb if r['id'] in n['clb_alignment']['condition_source_ids'])
    resource=n['language_resources']
    bp=n['task_blueprint'];tasktext=esc(json.dumps(bp,ensure_ascii=False,indent=2))
    knowledge=n['clb_alignment'].get('knowledge_strategy_reference')
    if knowledge:conditions+=''.join(f'<li><a href="sources/clb-2012.pdf#page={p}">CLB 口语知识与策略 · PDF {p}</a></li>' for p in knowledge['pdf_pages'])
    cards.append(f'<details class="node" data-level="{esc(n["level_candidate"])}" data-family="{esc(n["family_id"])}"><summary>{esc(n["id"])} · {esc(n["label"])}</summary><h3>原创子目标</h3><ol>{lis}</ol><h3>GSE 条目参考</h3><p>下表分数属于出版社条目，不能直接赋给本App节点。对应关系为候选。没有直接对应时明确保留缺口。</p><table><tr><th>原文</th><th>GSE</th><th>技能</th><th>出处</th><th>关系</th></tr>{rs}</table><h3>CLB 条件原文</h3><p>{esc(n["clb_alignment"]["relation"])}</p><ul>{conditions}</ul><h3>任务蓝图</h3><pre style="white-space:pre-wrap">{tasktext}</pre><h3>语言资源</h3><p>词汇领域：{esc(resource["vocabulary_domains"])}<br>表达功能：{esc(resource["expression_functions"])}<br>语法领域：{esc(resource["grammar_domains"])}</p><h3>评价</h3><p>各子目标分别记录独立成功、部分完成、未完成、不可判定；父目标的掌握须覆盖其关键子目标。保留音频和支持记录，并做迁移与延迟检查。评分阈值待校准。</p></details>')
report='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>能力地图：GSE / CLB 补充版</title><style>body{font:16px/1.7 system-ui;max-width:1160px;margin:40px auto;padding:0 24px;color:#223}h1,h2{line-height:1.3}details{border:1px solid #ccd;border-radius:10px;padding:14px;margin:12px 0}summary{cursor:pointer;font-weight:650}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:9px;border:1px solid #ddd;text-align:left}a{color:#245cb0}select,input{padding:8px;margin-right:10px}.note{background:#eef3fb;padding:18px;border-radius:10px}</style><h1>长期能力地图：GSE / CLB 补充版</h1>'''
report+=f'<p>保留 {len(mapdata["nodes"])} 个原节点，细化为 {len(children)} 个原创子目标。数据版本：{esc(mapdata["version"])}</p>'
report+='<div class="note"><b>使用边界</b><p>按用户要求假定授权已通过。本版是全部节点的细化与标准对应草案；出版社原文、条目分数及CLB—GSE官方关系有出处，本App节点到标准的关系仍需语义核查和测评校准。候选关系不会被标成官方等价。</p></div>'
empty_nodes=[n['id'] for n in mapdata['nodes'] if not n['gse_alignment']['candidate_objectives']]
empty_children=[c['id'] for c in children if not c['gse_candidate_links']]
report+=f'<h2>已补资料</h2><p>GSE 成人通用、职业、学术目标：{len(gse)} 条记录（含跨套重复）；语法目标：{len(grammar)} 条；Pearson 2024 CLB—GSE 对应：{len(official)} 条；CLB 听说条件原文：{len(clb)} 页。</p><p><a href="curriculum_map.json">完整地图 JSON</a> · <a href="subtargets.csv">子目标 CSV</a> · <a href="README.md">数据说明与后续核查要求</a> · <a href="verification.json">校验与缺口</a> · <a href="sources/download_manifest.json">新增下载清单</a></p>'
report+=f'<h2>对应状态</h2><p>{len(mapdata["nodes"])-len(empty_nodes)} 个父节点有GSE功能候选，{len(empty_nodes)} 个父节点没有直接候选。{len(children)-len(empty_children)} 个子目标有GSE候选，{len(empty_children)} 个尚无可靠候选；所有子目标均有CLB条件来源定位。没有候选不表示能力不存在，也不能由模型补造标准条目。全部本App对应关系仍待逐项语义评审。</p>'
report+='<h2>逐节点细化与引用</h2><input id="query" placeholder="搜索节点、目标或表达"><select id="level"><option value="">全部阶段</option>'+''.join(f'<option>{k}</option>' for k in LEVELS)+'</select><span id="count"></span>'
report+=''.join(cards)
report+='''<script>function filter(){let q=document.querySelector('#query').value.toLowerCase(),l=document.querySelector('#level').value,c=0;document.querySelectorAll('.node').forEach(n=>{n.hidden=!!((l&&n.dataset.level!==l)||(q&&!n.textContent.toLowerCase().includes(q)));if(!n.hidden)c++});document.querySelector('#count').textContent=c+' 个节点'}document.querySelector('#query').addEventListener('input',filter);document.querySelector('#level').addEventListener('change',filter);filter()</script></html>'''
(ROOT/'report.html').write_text(report)
print(json.dumps({'nodes':len(mapdata['nodes']),'subtargets':len(children),'gse':len(gse),'grammar':len(grammar),'official_clb_gse':len(official),'clb_condition_pages':len(clb),'empty_gse_nodes':[n['id'] for n in mapdata['nodes'] if not n['gse_alignment']['candidate_objectives']]},ensure_ascii=False))
