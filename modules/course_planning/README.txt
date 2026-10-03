当前状态（2026-10-03）：后端与iPhone实现位于 ../../backend/ 和 ../../ios/；启动、实际合同、测试与边界见 ../../README.txt。下文为保留的初始开发设计。

课程规划与生成模块：Python 开发设计 v1

阅读入口：design.html；结构化设计：design.json。
总体结构沿用四节点：调度 → 教学任务 → 生成课程与音频 → 质检与保存。
八个内部组件与大模型/规则职责在设计文档中展开。

contracts.schema.json 和 contracts.examples.json 为首版核心接口草案。
M1 开发时还需把学习步骤、资源ID、附加复习目标、预算及请求参数正式纳入合同。
ports.py 仅定义供应商和存储接口；schema.sql 未执行；没有已运行的生成服务。
生成文档：python -m modules.course_planning.build_design_docs

开发顺序：
M1 合同完善、目标调度、可恢复任务队列。
M2 模型文本生成、任务逻辑检查、20节既有课程回归适配。
M3 实际音频生成与核查、固定版本发布。
M4 能力模块和会话模块联调，测量延迟、成本与学习效果。

测试依赖：jsonschema==4.25.1。
地图模块读取与快照校验不依赖此包。
