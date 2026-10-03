import {useState,useHostTheme,H1,H2,Text,Select,Table,Link} from "cursor/canvas";
const components=[{"id": "scheduler", "name": "目标调度", "implementation": "rules", "input": ["LearnerProfile", "用户需求和时间", "TargetDefinition候选"], "output": "内部LearningPlan", "items": ["证据不足先选低负担诊断；尚未检查不等于不会", "优先当前交流阻碍和到期保持检查", "选择需求相关缺口，检查理解、互动修复的长期遗漏", "建议前置可跳过，不推导整个等级掌握", "记录选择理由、证据ID和其他候选"]}, {"id": "resources", "name": "资源选择", "implementation": "rules_with_optional_model_review", "input": ["LearningPlan", "用户词义理解与调用记录", "已采纳标准参考", "词库候选"], "output": "内部ResourceSelection", "items": ["按词义ID而非单词字符串排除已掌握资源", "认识但提取失败的表达进入练习，不重新解释整遍", "GL、SSGL为成人默认候选；YL需明确开启", "GSE未分级和星号状态保留，不自动给课程定级", "候选词必须与实际任务相关，主题命中不等于教学适配", "必要新资源必须在测评前确认理解，或记录支持，不据此误判沟通能力"]}, {"id": "assignment", "name": "教学任务构建", "implementation": "rules", "input": ["LearningPlan", "ResourceSelection", "固定目标合同"], "output": "TeachingAssignment", "items": ["用户、地图和能力摘要版本", "一个主目标与单独记录的附加目标", "明确的学习目的与理由", "主题、输入和支持条件", "已知、新学及复习资源", "学习、应用及独立变体要求", "目标必要意义和允许改述", "任务模式与音频证据要求"]}, {"id": "generator", "name": "文本与任务生成", "implementation": "LLM", "input": ["TeachingAssignment", "目标合同", "已审核模板或示例"], "output": "LessonPackage draft", "items": ["先检查是否有版本及条件兼容的审核模板", "无匹配模板时模型按结构化合同生成", "中文意图→英文说法→必要解释→个人替换→遮答案表达→信息差应用", "具体化双方可见事实、角色私有信息、回应规则、关键意义和可接受结果", "独立变体改变影响结果的条件，不只换名字", "生成pass/partial/fail/unjudgeable锚点，但锚点不是已校准评分器"]}, {"id": "text_qa", "name": "文本与任务质检", "implementation": "rules_and_LLM", "input": [], "output": "QualityReport", "items": ["Schema、固定版本和目标引用", "逻辑限制与可行结果", "输入资源已学或支持被明确记录", "阶段、输入条件与允许帮助", "角色不替用户完成关键动作", "独立变体不暴露示例答案", "评分检查只评价主目标必要意义", "用户拒绝、个人立场或不熟悉专业知识不算语言失败", "客户端负载不含对方私有信息和评分锚点"]}, {"id": "audio", "name": "音频生成与复用", "implementation": "speech_service_and_rules", "input": "text_checked LessonPackage", "output": "音频资产引用与生成状态", "items": ["为已审核文本生成或匹配适配音频", "学习示例和测评输入分别标用途", "异步执行，固定声音配置和文本版本", "网络失败按阶段重试，不重做已完成文本"]}, {"id": "audio_qa", "name": "音频质检", "implementation": "speech_tools_and_rules", "input": [], "output": "阶段数据与检查状态", "items": ["资产存在且能解码播放", "关键词、数字、否定与文本一致", "语速、长度与清晰度符合任务条件", "测评字幕和提示显示规则", "语音转写对照是辅助检查，不是绝对正确性证明"]}, {"id": "publication", "name": "课程保存与交付", "implementation": "rules", "input": [], "output": "LessonPackage approved", "items": ["仅必要文本和音频检查通过才能learner_ready", "课程版本发布后不可原位改写，修订生成新版本", "保留模型、提示、地图、规则、资源和音频版本", "服务端保留全部角色和评分内容；由会话服务按阶段投影公开负载", "未通过的草稿可保存研究，但不得成为用户可见课程"]}];
const milestones=[{"id": "M1", "deliverable": "合同、调度规则及任务队列骨架", "acceptance": ["同输入和规则版本可重现调度", "已知资源不重复解释", "一次课程一个主目标", "失败和不确定证据可触发诊断", "幂等及重启恢复"]}, {"id": "M2", "deliverable": "文本生成与QA", "acceptance": ["真实供应商结构化输出", "20节样例字段映射", "注入错误及正确改述回归", "未通过不能发布", "缺少模板正确进入needs_review"]}, {"id": "M3", "deliverable": "音频链路与课程发布", "acceptance": ["实际声音与文本核查", "公开/伙伴/评分负载隔离", "版本不可覆盖", "重试不重复计费阶段或重复发布"]}, {"id": "M4", "deliverable": "与能力模块及会话模块联调", "acceptance": ["真实用户摘要读入", "会话实际支持记录可评价", "真实延迟及成本基线", "保持与迁移试点；不预先承诺最快"]}];
const states=["queued", "planning", "generating_text", "checking_text", "generating_audio", "checking_audio", "approved", "needs_review", "failed", "cancelled"];
export default function CoursePlanning(){
 const t=useHostTheme(); const [selected,setSelected]=useState(components[0].id);
 const c=components.find(x=>x.id===selected)!;
 return <main style={{maxWidth:1100,margin:"0 auto",padding:28,color:t.text.primary,background:t.bg.editor}}>
 <H1>课程规划与生成：Python 开发设计</H1>
 <Text>2026-10-03 · 地图 1.0.1-model-reviewed · 设计 v1</Text>
 <Text>总体流程：调度 → 教学任务 → 生成课程与音频 → 质检与保存。下面八个组件是内部展开，保留整体架构。</Text>
 <H2>八个内部组件与实现职责</H2>
 <Table headers={["子模块","实现方式","输出"]} rows={components.map(x=>[x.name,x.implementation,x.output])}/>
 <Select value={selected} onChange={setSelected} options={components.map(x=>({value:x.id,label:x.name}))}/>
 <H2>{c.name}</H2><Text>输入：{Array.isArray(c.input)?c.input.join("、"):c.input}</Text>
 <ul>{c.items.map((x,i)=><li key={i} style={{marginBottom:8}}>{x}</li>)}</ul>
 <H2>技术结构与交付边界</H2>
 <Text>FastAPI 接收请求，独立 Python Worker 执行生成；PostgreSQL 保存业务数据及任务队列；音频保存在对象存储。地图仓库只读，模型与语音供应商通过接口替换。</Text>
 <Text>目标选择与发布由规则决定。大模型生成文本和任务，辅助语义质检。语音工具生成并核查音频。服务端完整课程包包含角色私有事实，App 只接收当前阶段的公开学习内容。</Text>
 <H2>异步任务状态</H2><pre style={{whiteSpace:"pre-wrap",padding:16,background:t.bg.elevated,fontSize:13}}>{states.join(" → ")}</pre>
 <Text>同用户幂等键去重；阶段可恢复；过期 Worker 不能覆盖新结果；课程发布和完成事件同事务保存。失败草稿保留审核状态。</Text>
 <H2>开发顺序与验收</H2><Table headers={["阶段","交付","验收"]} rows={milestones.map(x=>[x.id,x.deliverable,x.acceptance.join("；")])}/>
 <H2>已保存内容</H2>
 <Text>地图读取、校验和快照导出代码已经实现。课程模块当前交付开发设计、核心合同草案、数据库草案和 Python 接口；生成服务尚未实现，SQL 未执行。</Text>
 <Text><Link href="/Users/lhy/Workspace/SayWithV3/modules/course_planning/design.html">完整设计与接口示例</Link> · <Link href="/Users/lhy/Workspace/SayWithV3/modules/course_planning/contracts.schema.json">JSON Schema</Link> · <Link href="/Users/lhy/Workspace/SayWithV3/modules/course_planning/schema.sql">数据库草案</Link> · <Link href="/Users/lhy/Workspace/SayWithV3/modules/curriculum/README.txt">地图模块运行说明</Link></Text>
 </main>;
}
