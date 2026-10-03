"""Generate interface schemas and a local engineering design document."""
from pathlib import Path
import html,json
R=Path(__file__).resolve().parent
d=json.loads((R/'design.json').read_text())
S={'type':'string','minLength':1}; A=lambda item:{'type':'array','items':item}
def obj(props,required):return {'type':'object','properties':props,'required':required,'additionalProperties':False}
defs={}
defs['TeachingAssignment']=obj({
 'schema_version':{'const':'1.0'},'assignment_id':S,'user_id':S,'map_version':S,
 'profile_version':{'type':'integer','minimum':0},'target_ids':{**A(S),'minItems':1,'maxItems':1},
 'reason':S,'context':S,'resource_plan':obj({'review':A(S),'focus':A(S)},['review','focus']),
 'difficulty':obj({'time_conflicts':{'type':'integer','minimum':0},'support':S},['time_conflicts','support'])
},['schema_version','assignment_id','user_id','map_version','profile_version','target_ids','reason','context','resource_plan','difficulty'])
defs['LessonPackage']=obj({
 'schema_version':{'const':'1.0'},'lesson_id':S,'lesson_version':{'type':'integer','minimum':1},
 'assignment_id':S,'map_version':S,'target_ids':{**A(S),'minItems':1,'maxItems':1},
 'learning_materials':{**A(obj({'intent_zh':S,'expression':S,'audio_ref':S},['intent_zh','expression'])),'minItems':1},
 'practice_task_ref':S,
 'independent_task':obj({'task_id':S,'task_version':{'type':'integer','minimum':1},
  'learner_facts':{'type':'object'},'partner_private_facts':{'type':'object'},
  'role_rules':A(S),'allowed_support':A(S),
  'assessment_contract':{'type':'object','required':['critical_checks','accept_correct_paraphrase'],
   'properties':{'critical_checks':{**A(S),'minItems':1},'accept_correct_paraphrase':{'type':'boolean'}}}
 },['task_id','task_version','learner_facts','partner_private_facts','role_rules','allowed_support','assessment_contract']),
 'quality':obj({'status':{'enum':['draft','approved','needs_review']},'report_ref':S,'qa_version':S},['status']),
 'learner_ready':{'type':'boolean'},
 'provenance':obj({'model_version':S,'prompt_version':S},['model_version','prompt_version']),
 'example_notice':S
},['schema_version','lesson_id','lesson_version','assignment_id','map_version','target_ids','learning_materials','practice_task_ref','independent_task','quality','provenance'])
defs['LessonPackage']['allOf']=[{
 'if':{'properties':{'quality':{'properties':{'status':{'const':'approved'}}}}},
 'then':{'properties':{'quality':{'required':['report_ref','qa_version']},'learning_materials':{'items':{'required':['audio_ref']}}}}
},{'if':{'required':['learner_ready'],'properties':{'learner_ready':{'const':True}}},
 'then':{'properties':{'quality':{'properties':{'status':{'const':'approved'}}}}}}]
defs['GenerationJob']=obj({'schema_version':{'const':'1.0'},'job_id':S,'user_id':S,
 'state':{'enum':d['workflow_states']},'row_version':{'type':'integer','minimum':1},
 'assignment_id':S,'result_lesson_id':S,'result_lesson_version':{'type':'integer','minimum':1},
 'error':{'type':['object','null']},'created_at':{'type':'string','format':'date-time'}
},['schema_version','job_id','user_id','state','row_version','created_at'])
defs['QualityReport']=obj({'schema_version':{'const':'1.0'},'report_id':S,'job_id':S,'lesson_id':S,
 'lesson_version':{'type':'integer','minimum':1},'stage':{'enum':['text','audio','publication']},
 'decision':{'enum':['pass','fail','unjudgeable']},'checker_version':S,
 'checks':A(obj({'id':S,'passed':{'type':['boolean','null']},'reason':S},['id','passed','reason']))
},['schema_version','report_id','job_id','lesson_id','lesson_version','stage','decision','checker_version','checks'])
schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'urn:saywith:course-planning:design-v1',
 'title':'Course planning design contracts','description':'设计合同，不代表服务已实现；供应商结构化输出需适配其支持的Schema子集', '$defs':defs}
(R/'contracts.schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2))
old=R.parents[1]/'research/system-dataflow-2026-10-02/contracts.examples.json'
fixtures=json.loads(old.read_text());examples={k:fixtures[k] for k in ['TeachingAssignment','LessonPackage']}
examples['LessonPackage']['learner_ready']=False
examples['GenerationJob']={'schema_version':'1.0','job_id':'job001','user_id':'u001','state':'queued','row_version':1,'created_at':'2026-10-03T18:00:00+08:00'}
examples['QualityReport']={'schema_version':'1.0','report_id':'qa001','job_id':'job001','lesson_id':'ls001','lesson_version':1,'stage':'text','decision':'pass','checker_version':'qa-v1','checks':[{'id':'target_contract','passed':True,'reason':'接口演示，未执行真实模型检查'}]}
(R/'contracts.examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2))
e=lambda s:html.escape(str(s))
sections=''.join('<section><h2>'+e(c['name'])+'</h2><p><b>实现：</b>'+e(c['implementation'])+'</p><ul>'+''.join('<li>'+e(v)+'</li>' for v in c.get('logic',c.get('checks',c.get('required',[]))))+'</ul>'+('<p>'+e(c['failure'])+'</p>' if 'failure'in c else '')+'</section>' for c in d['components'])
api=''.join('<tr><td>'+e(x['method'])+'</td><td>'+e(x['path'])+'</td><td>'+e(x.get('request',''))+'</td><td>'+e(x['response'])+'</td></tr>' for x in d['interfaces'])
milestones=''.join('<h3>'+e(m['id']+' '+m['deliverable'])+'</h3><ul>'+''.join('<li>'+e(x)+'</li>' for x in m['acceptance'])+'</ul>' for m in d['milestones'])
doc='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>课程规划与生成模块开发设计</title><style>body{font:16px/1.65 system-ui;color:#24313c;background:#fafbfc;margin:0}main{max-width:1050px;margin:auto;padding:32px 24px}h1{font-size:28px}h2{font-size:22px;margin-top:36px}h3{font-size:18px}a{color:#145782}pre{white-space:pre-wrap;background:#edf2f5;padding:16px;font-size:13px}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;border-bottom:1px solid #dce1e6;text-align:left;vertical-align:top}.note{padding:14px;border-left:3px solid #778d9d;background:#edf2f5}li{margin:6px 0}</style><main>
<h1>课程规划与生成模块开发设计</h1><p>2026-10-03 · Python 后端 · 固定地图 1.0.1-model-reviewed · 设计 v1</p>
<p class="note">本文是开发设计。地图读取、校验和快照导出代码已经整理；课程规划、供应商调用、异步任务、语音生成与发布服务尚未实现。SQL未执行到任何数据库。</p>
<p>沿用已确认的总体结构：调度 → 教学任务 → 生成课程与音频 → 质检与保存。下述8个子模块是内部开发分工，不替换总体图。</p>
<p><b>初版：</b>Python + FastAPI + 独立异步Worker + PostgreSQL任务队列和业务存储 + 音频对象存储。地图通过只读仓库访问，模型与语音通过可替换接口调用。</p>
<p><a href="design.json">结构化设计</a> · <a href="contracts.schema.json">JSON Schema</a> · <a href="contracts.examples.json">接口示例</a> · <a href="schema.sql">数据库草案</a> · <a href="ports.py">Python接口</a></p>
<h2>输入、输出与边界</h2><p>输入：固定版本的TargetDefinition、LearnerProfile、需求与预算。输出：有审核状态的LessonPackage。内部负责目标和资源选择、生成、质检与发布；能力掌握更新由模块2执行，实时角色状态和公开负载投影由会话服务执行。</p>
SECTIONS
<h2>异步状态与失败恢复</h2><p>STATES</p><ul>RULES</ul>
<h2>API合同</h2><div style="overflow:auto"><table><thead><tr><th>方法</th><th>路径</th><th>输入</th><th>输出与边界</th></tr></thead><tbody>__API_ROWS__</tbody></table></div>
<h2>数据库与事件</h2><p>保存learning_plans、teaching_assignments、generation_jobs、lesson_versions、quality_reports、audio_assets和outbox_events。公开课程版本不可原位改写；用户数据与角色私有负载分开授权读取。模型输出不能自行设置发布通过。</p>
<h2>已有20节课程如何接入</h2><p>将research/course-qa-2026-10-02的20节课程作为任务合同与错误注入回归样例。它们含学习步骤、角色规则和独立变体，但没有真实声音，也未调用生产生成器，须显式字段适配，不能整包发给App。</p><ul><li>main_objective_id → target_ids中的主目标</li><li>learning → learning_materials与学习步骤</li><li>supported_practice → 有提示练习任务</li><li>independent_task、role_response_rules、assessment → 独立任务合同及私有角色规则</li><li>release、audio_assets → QA与资产状态，不继承为上线许可</li></ul>
<h2>开发顺序与验收</h2>MILESTONES
<h2>仍需确定</h2><ul>OPEN</ul>
<h2>接口示例</h2><p>示例ID用便于阅读的缩写；生产数据库设计使用UUID，需在实现时统一。示例状态只展示格式，不代表真实服务已执行。Schema只检查结构，事实、角色、质量和语音需要其他检查。</p>EXAMPLES
<p>语言选择参考：<a href="https://fastapi.tiangolo.com/async/">FastAPI异步与并发说明</a>。部署和队列仍需结合实际请求量测试。</p>
</main></html>'''
doc=doc.replace('SECTIONS',sections).replace('STATES',e(' → '.join(d['workflow_states']))).replace('RULES',''.join('<li>'+e(x)+'</li>' for x in d['workflow_rules'])).replace('__API_ROWS__',api).replace('MILESTONES',milestones).replace('OPEN',''.join('<li>'+e(x)+'</li>' for x in d['open_decisions'])).replace('EXAMPLES',''.join('<h3>'+e(k)+'</h3><pre>'+e(json.dumps(v,ensure_ascii=False,indent=2))+'</pre>' for k,v in examples.items()))
(R/'design.html').write_text(doc)
print('schemas, fixtures and design document written')
