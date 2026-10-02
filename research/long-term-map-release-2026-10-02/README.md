# 词义全量导出与长期课程地图上线候选

## 当前交付

本目录包含完整的公开 Toolkit 词义快照，以及经过数据规则优化的长期课程地图后端包。地图版本为 `1.0.0-rc1`。它可以接入后端与课程审核流程；全量用户课程尚未达到公开上线条件。

这项区别来自实际缺口：当前没有全部具体任务与评分样例，没有对实际生成模型和语音链路进行验证，也没有真人学习者的诊断、迁移与保持校准。JSON 能解析不能证明这些环节已经完成。

## 1. GSE 词义取得方法

从官方页面 `https://www.english.com/gse/teacher-toolkit/user/vocabulary` 的前端脚本核实：

- 查询：`GET api/v1/vocabulary/search`。
- 参数包括 `query_string`、`page`、`size`、`sort`、`filters`。
- 当前完整查询：`query_string=*`，三类人群 `GL / SSGL / YL`，网页默认范围 `10–90`，主题和词性不设限制。
- 网页另有选中词义的 `list` 接口及 XLS 导出功能。当前本地导出使用相同查询接口的完整分页响应，没有绕过登录、验证码或访问限制。

按用户指示假定使用与导出授权已经通过；本目录没有声称审阅了授权证明。

完整查询返回 **41,402 个唯一词义**：成人通用 34,794；成人软技能 3,513；少儿 3,095。

完整查询实际包含 **1,357 个 `N/A` 未分级词义**。改变等级范围后这些条目不再返回，所以单纯加总整数等级分段会少条目。最终采用完整范围分页，共42页，原始响应与哈希保留在 `vocabulary/raw/`。

另有 **540 个出版社星号条目**，保留原始星号和 `temporaryGse` 等返回字段，不能擅自视为确定难度。SQLite 的数字分数与 `gse_raw`、`gse_status` 分列，`N/A` 数字分数为 NULL。

字段含词义ID、表达、释义、例句、GSE/CEFR、人群、词性、搭配、变体、主题路径、地区信息和音频链接。JSONL 与 SQLite 原始载荷保留全部返回字段；CSV包含主要字段。音频没有下载。

“完整”指当前公开接口的这三个词汇人群范围，与Pearson内部未发布数据无关。网站没有给出稳定公开API服务承诺，运行中的App宜读取已获授权的本地版本，并通过正式的数据交付方式维护更新。

### 文件

- `vocabulary/gse_vocabulary.jsonl`：完整词义及全部返回字段。
- `vocabulary/gse_vocabulary.csv`：主要字段，方便分析。
- `vocabulary/gse_vocabulary.sqlite`：词义查询、分数状态、全文索引。
- `vocabulary/topics.json` / `grammaticalCategories.json`：主题与词性分类。
- `vocabulary/manifest.json`：范围、总数、分页、来源和文件摘要。

## 2. 地图优化

地图保留140个原能力分组作为兼容索引，但它们不是固定节点数目标。现有学习目标改为424个：把“接受或婉拒邀请”、感谢/道歉/祝贺的表达与回应分别拆开。分组只用于导航；真正选课和存证据使用学习目标ID与任务条件。

其他变化：

1. 发音、词句提取、语法与策略是贯穿各阶段的支持能力。旧阶段只作首次引入参考。
2. 相似沟通动作增加共享关系，便于安排迁移练习；不自动复制掌握状态。
3. 原词面检索得到的GSE/CLB候选只作研究参考，不能作为官方判级依据。
4. 出版社原文听说目标跨套去重为1,154条（坐标修正后），保留各原文来源与分数；相同说法分数不同的来源不取平均。
5. 词义资源与任务功能连接，通过主题查询产生候选，随后核查词义是否真的为该任务所需。
6. 未分级、星号、少儿资源各有处理规则，成人默认只用GL/SSGL。
7. 每个学习目标具有生成合同、可观察判断、低可信度不可判定规则和版本迁移。
8. 后端数据检查通过后，仍要求具体课程审核和实际生成/评分验证。

### 地图文件

- `curriculum_map.json` / `curriculum_map.schema.json`：后端地图与结构规范。
- `learning_objectives.csv`：当前424个目标。
- `official_oral_objectives.json`：去重后的官方听说目标参考库。
- `migration.json`：原420个目标到现424个目标的迁移。
- `node_review.json` / `optimization_audit.json`：逐节点规则调整与未解决问题。
- `runtime_policy.json`：选目标、选词义、存证据和生成限制。
- `task_fixture.json`：带双方日程、角色规则、评分锚点和独立变体的具体改期任务，用于后端正反例检查；音频与教学审核尚未完成。
- `release_policy.json`：公开上线检查状态。
- `verification.json`：本次实际校验结果。

## 3. 接入及上线顺序

后端可以现在导入词义库和课程地图，按“一个主学习目标 + 必要支持目标”设计课程。它不能把全部424个目标立即设为自动发布。

上线每个目标前，制作并审核至少一套具体教学/互动任务、独立测评变体和模型辅助评分样例，再用实际模型、音频与语音识别链路检查生成质量和评分一致性。只有通过检查的目标进入用户课程池；候选目标仍留在长期地图中。

完整词义数据也不能让系统仅凭用户总等级判断哪些词已经会说。用户资源状态须区分“听懂、能够提取、能够在新任务组合使用”。

目前未证明最快路径或全部CEFR等级的测评准确度。地图展示的是课程阶段参考；未经校准不报告用户正式GSE分数。

## 复现

```bash
python3 research/long-term-map-release-2026-10-02/export_vocabulary.py
python3 research/long-term-map-release-2026-10-02/build_release.py
python3 research/long-term-map-release-2026-10-02/calibrate.py
python3 research/long-term-map-release-2026-10-02/assessment_calibration.py
python3 research/long-term-map-release-2026-10-02/verify_release.py
```

导出程序可复用已下载的页面；更新快照时应保存为新版本，不把旧原始响应与新版本混合。
