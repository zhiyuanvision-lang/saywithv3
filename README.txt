SayWith V3 — Python 教学后端 + iPhone 原生 App，开发版 0.1.0

一、实现范围
1. 地图与资源：读取已审查地图（140分组、424目标），检索词义资源；导入与归一化资料；记录来源、人工审查；发布不可变地图版本；新课使用当前发布版，已发布课程继续固定旧版。
2. 表现评价与能力更新：保存实际任务条件、提示、录音和最终识别文本；模型按目标合同评价，程序校验证据引用；事务更新独立、保持、迁移及复习需求。失败原因保留为待验证假设。
3. 课程规划与生成：调度新学/巩固/覆盖 → 下达教学任务 → DeepSeek生成并修订课程 → 字节合成/识别核查音频 → 固定版本课程发布。独立任务必须改变具体条件。任务队列支持重试、断点续作、租约、取消、幂等和并发版本检查。
4. 教学执行：iPhone上的意图理解、英文声音、中文解释、个人替换、遮答案试说；有提示对话、换条件独立交流、反馈。后端管理角色事实、提示和阶段；App收不到私有答案与评价合同。
5. 基础设施：SQLite本地开发、PostgreSQL集成验证；隔离音频资产；API/worker独立进程；事务事件记录、运行指标、模型与规则版本追踪。

二、本机运行（工作目录为本文件所在目录）
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
.venv/bin/pip install -e . --no-deps
复制 .env.example 为 .env，再填入服务端配置。
终端1：.venv/bin/python -m backend serve --host 127.0.0.1 --port 8083
终端2：.venv/bin/python -m backend worker
接口文档：http://localhost:8083/docs
健康检查：http://localhost:8083/health
只启动API不启动worker，课程会停留在排队状态。

本地 .env 已根据用户授权参考 ../SayWith/ 的配置写入；文件被Git忽略，权限600。
SAYWITH_MODE=provider：真实DeepSeek文本 + 字节语音服务。
SAYWITH_API_BASE=https://api.deepseek.com
SAYWITH_TEXT_MODEL、SAYWITH_REVIEW_MODEL：采用现有账号支持的模型。
SAYWITH_API_KEY：DeepSeek密钥。
DOUBAO_API_KEY：字节语音密钥。
DOUBAO_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
DOUBAO_TTS_RESOURCE_ID=seed-tts-2.0
DOUBAO_TTS_SPEAKER=en_female_dacey_uranus_bigtts
SAYWITH_ADMIN_TOKEN：自行生成的管理端密钥；未配置时所有管理接口禁止访问。

SAYWITH_MODE=fixture：不调用外部服务。只有 ARRANGE.A2.s2 的固定约时间用例；声音是测试静音，不能识别真实录音；只能做界面/合同/流程测试，绝不计入用户能力。其他目标需真实服务。App会显示测试模式。

三、iPhone App
项目：ios/SayWithV3.xcodeproj，scheme SayWithV3，最低iOS17，Swift6/SwiftUI。
如修改 ios/project.yml，先运行 xcodegen generate --spec ios/project.yml。
在Xcode选择iPhone模拟器并运行。模拟器默认服务地址：http://localhost:8083。
登录页参考旧版SayWith，仅提供手机号验证码、微信和Apple三种方式。复用旧版身份验证服务，为新版关联稳定的学习账号；旧版学习数据不会自动导入。
访问令牌和可轮换刷新令牌一起存入设备专属Keychain，同机重启自动恢复、访问令牌到期自动刷新；退出登录撤销当前会话。网络暂时失败保留凭据，刷新令牌过期或撤销后需要重新登录。模型密钥只存于后端。
首次身份登录可接管本机已有的匿名学习记录（该身份尚未建立新版账号时）；同一服务下的练习恢复状态按用户ID隔离。
设置可改变主题/参考难度；实际任务证据参与后续推荐。参考难度不是英语认证等级。
生成任务与学习会话可在重启后恢复；提交输入失败可重试同一请求。
录音要求：16kHz、单声道PCM16 WAV；App自动录制此格式，每次最多90秒。
用户录音发送后端及字节语音服务；App设置页包含说明。

连接真实iPhone：在Xcode配置自己的签名团队，开启手机开发者模式，使用HTTPS后端地址。
同网调试可用Mac的 .local 主机名，同时以 --host 0.0.0.0 启动后端；localhost在手机上指手机本身。
真机首次安装可在构建时指定 SAYWITH_BACKEND_URL=http://你的Mac主机名.local:8083，写入App配置；也可在App中修改地址。模拟器默认继续使用localhost。首次访问需要允许本地网络。
当前真机开发构建使用 http://lhydeMacBook-Pro.local:8083；后端已绑定0.0.0.0供同网访问。
Xcode未登录账号时，可用自己的App Store Connect API密钥配合 -authenticationKeyPath、-authenticationKeyID、-authenticationKeyIssuerID 和 -allowProvisioningUpdates 完成开发签名。密钥不放入代码或App。
2026-10-03：已在连接的iPhone 12 Pro Max上安装开发签名版本；真机启动记录见 verification/device-install-2026-10-03.json。麦克风录音和完整真人学习流程仍待人工验收。

四、容器
配置 .env 中随机 SAYWITH_DB_PASSWORD 后：docker compose up --build -d
包含PostgreSQL、API与worker，持久化数据库和音频卷；API默认仅绑定127.0.0.1:8083。
对外服务需在入口配置HTTPS与访问控制。新数据库不自动合并已有SQLite记录。
当前实现采用 backend/store.py 的四个SQLAlchemy表（documents、users、generation_jobs、outbox_events）；modules/course_planning/schema.sql 是历史设计草案，没有执行。后续结构迁移需版本化处理。
事务事件当前用于审计/后续消费者读取，不含外部消息代理投递器。

五、合同与代码对应
原始11种数据示例：research/system-dataflow-2026-10-02/contracts.examples.json。
实际Pydantic类型：backend/contracts.py；导出JSON Schema：backend/contracts.schema.json。
接口定义：backend/openapi.json；运行时 /openapi.json。
地图与资源：modules/curriculum/ + backend/curriculum.py。
评价与能力：backend/assessment.py。
规划与生成：backend/planning.py、generation.py、providers.py、byte_speech.py。
会话与公开投影：backend/sessions.py。
持久化/队列/事件：backend/store.py；接口与权限：backend/app.py。
模块间传递校验后的JSON；数据包含地图、课程、模型、规则版本；服务端可信字段覆盖模型输出。
旧设计入口 modules/course_planning/design.html 供追溯，本文件及实际代码描述当前实现。

六、验证与边界
.venv/bin/python -m pytest -q
.venv/bin/python -m backend validate
xcodebuild test -project ios/SayWithV3.xcodeproj -scheme SayWithV3 -destination 'platform=iOS Simulator,name=iPhone 17' CODE_SIGNING_IDENTITY=-
界面集成测试须启动 fixture API 与 worker，建议使用独立测试数据库。
验证记录：verification/implementation-2026-10-03.json。

当前已具备端到端开发版；仍需真人录音、真实学习效果与评价一致性试点。
“独立多次完成/隔期保持/换条件应用”使用透明初始规则，未经用户数据校准；不生成虚构的发音分数，也不从文字判断流利度。不能据此承诺最少学习时间或母语水平。
匿名账户仅允许fixture开发验证，iOS界面测试须显式传入 --ui-test-anonymous；provider模式禁止新建匿名账户。正式发布前仍需补配额/费用管理、个人数据导出/删除和运营验收。

七、v6 学习界面（2026-10-03）
按 docs/v6-app-learning-stage.md 实现四阶段原生页面：学习 → 三轮引导 → 独立应用 → 任务反馈。
学习提供中英文表达、常速示范播放、可展开对话与逐句高亮、跟读/回听/重试；完成跟读后进入引导练习。
跟读只记录学习证据。ASR确认的是识别文本与示范的接近程度，不能当作发音分数。
三轮练习由后端生成和审核，失败草案最多修复两次；仍不通过时保留学习进度并提示重试。
提示面板分意图、句型、完整示例和已学表达，使用记录保存在服务端。独立任务按 interaction_policy 控制文字、重复和翻译。
返回引导或退出会保存 abandoned 记录，不自动生成失败评价；独立任务的答案帮助入口会结束这次独立检查。
辅助文字输入使用独立面板，避免键盘挤占固定录音区域。最大辅助字体下，任务条件放入可完整滚动的面板。
新增接口：POST /v1/sessions/{id}/shadow、/transition；/next 设置 advance_round=true 启用三轮流程。
实现：ios/SayWithV3/LessonScreen.swift、backend/teaching_support.py；合同及 OpenAPI 已更新。
fixture 界面测试使用 localhost:8086，须单独运行 fixture API/worker；模拟器使用默认临时签名，不能关闭签名，否则 Keychain 不可用。
本次验证记录：verification/v6-learning-2026-10-03.json。
连续对话按真实消息自然高度排列，用户查看历史时不强制跳转；只在位于底部时跟随新消息。
GET /v1/recommendations 返回到期推荐、时长及已学目标；首页展示今日复习与继续学习，已学内容放在进展页面。
生成及创建会话传 entry_kind=review。复习直接进入会话并播放角色首句，录音由用户按住启动，松开发送，上滑松开取消；需要答案时保存未完成记录并转回引导。
复习后的“换内容再试”会重新生成任务，避免复用已看到的独立答案。
review_metadata 保存目的、策略版本、基准尝试、实际间隔及条件变化；不同场景本身不再自动赋予迁移成功。
迁移判定要求经验证的专门条件；当前新增条件记录供后续审核与校准，不伪造迁移结论。
返回箭头保留会话，继续学习恢复已保存阶段；更多菜单中的“退出本次任务”才结束未完成任务。
默认字体按系统语义样式映射到正文17pt、表达和任务标题20pt、释义15pt、角色与状态13pt；左右20pt、卡片内18pt。支持系统暂停/续播和首次播放失败后的手动播放。
首页标题使用可缩放的26pt，音频播放以系统喇叭/暂停图标呈现，保留VoiceOver操作说明。

八、腾讯云新版（2026-10-03）
正式应用名称、Bundle ID、图标和法律/支持地址沿用 ../SayWith；iOS 1.0.6 (601)。
导航为学习、进展、我的；课程地图由后端用于调度。Release 默认连接 https://api.saywith.zhiyuanv.com/learning，支持基址路径与私有音频请求；不显示调试地址输入。
GET /v1/recommendations 的 next_learning 与课程调度使用同一选择函数；读取推荐不会创建课程或教学记录。
已学清单同时读取真实学习接触记录和能力证据；未证明独立能力的目标可以巩固复习，但不称为保持或迁移成功。fixture 不计入真实已学记录。
学习、三轮引导、独立应用、反馈、复习、恢复进度、偏好保存、提示/翻译/重听、音频上传和能力记录都有后端接口；前端按合同隐藏禁用操作。
生成要求明确 assessment_contract.acceptable_times；质检修复反馈给出具体字段和双方交集。音频对照识别 five o'clock 与 5:00 的等价形式，同时严格区分错误数字和否定。
腾讯云 SSH 别名 tengxun；运行目录 /opt/saywith-learning/current；数据为独立 PostgreSQL 数据库与 /opt/saywith-learning/var/media。API/worker 用 systemd，Nginx 在现有 HTTPS 域名的 /learning/ 路径转发。
部署模板与首次部署脚本位于 deploy/；密钥在服务器私有 .env 中。更新版本保留 previous 代码和 Nginx 备份，健康检查通过后再开放入口。不要将私有 runtime.env 或 var 中调试账号加入版本控制。
本次云端闭环记录：verification/cloud-learning-2026-10-03.json。语音链路验证使用合成录音，真人效果需手机验收。

全局意见反馈与v6对齐（2026-10-03）：
使用可拖动悬浮入口及我的页入口；分类、文本、最多4张图片、草稿恢复、幂等提交、历史、客服回复、补充消息和结束工单均接入旧版反馈库。后端使用独立受限数据库角色，客户端只持有自己的学习凭据。测试工单 5bb35262b72757948233320d170d4af9 已通过旧版后台工单接口确认可见。
页面按v6静态稿调整为纯箭头导航、独立原话/表达卡片、白色角色消息、蓝色用户消息、外置角色名、时间标签和全宽录音按钮。任务详情及用法进入按需打开的系统sheet，翻译图标在喇叭旁。辅助字号时任务条件进入滚动区，避免遮挡会话。
生成质检拒绝占位句型合成音频；结构错误进入最多两次修复。TTS使用明确的英语时间读法，ASR对照仍严格区分小时、分钟与否定。真实生成仍可能因内容或语音质检进入needs_review，不作为已发布课程。
对齐截图与验证记录：docs/v6-native-alignment-2026-10-03.md、verification/feedback-ui-2026-10-03.json。

全局查词、生词本与反馈导出（2026-10-03）：
我的页新增生词本与详情；所有课程英文、提示与记录支持点击查词，加入生词本按账号和词头去重，删除保留历史证据。收藏作为弱词汇练习信号进入课程规划；查词释义记入实际任务支持，不计为无帮助独立表现。说明见 docs/v6-vocabulary.md。
make feedback 将工单文字与图片导出到本项目 support.md 和 tmp/feedback-inbox，导出成功后自动关闭后台工单；之前已导出但仍待处理的工单也会关闭。make feedback-close 保留为同等命令。
