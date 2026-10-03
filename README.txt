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
首次建立匿名学习记录，访问令牌存入Keychain；模型密钥只存于后端。
设置可改变主题/参考难度；实际任务证据参与后续推荐。参考难度不是英语认证等级。
生成任务与学习会话可在重启后恢复；提交输入失败可重试同一请求。
录音要求：16kHz、单声道PCM16 WAV；App自动录制此格式，每次最多90秒。
用户录音发送后端及字节语音服务；App设置页包含说明。

连接真实iPhone：在Xcode配置自己的签名团队，开启手机开发者模式，使用HTTPS后端地址。
同网调试可用Mac的 .local 主机名，同时以 --host 0.0.0.0 启动后端；localhost在手机上指手机本身。
当前连接的iPhone关闭开发者模式，尚未完成真机安装/麦克风人工验收。模拟器编译和自动化流程已验证。

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
匿名账户适用于开发验证；正式发布前需补账号找回、配额/费用管理、个人数据导出/删除和运营验收。
