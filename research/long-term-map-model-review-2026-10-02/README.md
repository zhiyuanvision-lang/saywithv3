# 长期地图模型辅助审核 · 1.0.1

本次完成140个分组、424个目标及1,315条既有GSE候选关系的单一模型审核。它完成的是地图规格审核，不能代替具体课程、大模型/语音服务实测或真人效果证据。

## 判断方式

助手读取全部分组与子目标、候选原文和CLB条件参考，手工编写 `review_decisions.py` 的逐目标采纳矩阵、改写和边界说明。`build_review.py` 执行这些已写明的决定，保留原文、理由、采用用途和版本。没有用词面相似度阈值冒充语义审核，也没有独立专家或多个模型的交叉验证。

- 修改24个过于内部化或笼统的目标，使判断能通过实际回应、说明、复述或追问观察。
- 既有关系500条保留为部分参考，815条不采纳。关系数包含分组与子目标两层，不是不同出版社条目的数量。
- 223个目标具有已采纳的部分参考；201个目标保留原创定义，不强行填入GSE对应。
- 新选12个参考分配，例如用正式/非正式语体条目替代缺词改述，用他人信息改述替代只改述自己的表达。
- CLB继续提供条件参考，取消经GSE对照链条推导节点等级的使用方式。
- 所有等级仍是产品课程阶段索引，GSE源分数不能当用户正式成绩。

## 来源修复

重新处理PDF页边的PRO/AC标记和来源代码，防止页边标签混入目标句及 `topic(s)` 被误当条目结束。保留跨来源重复条目的旧ID别名；167条旧记录的技能或分数得到修正，8个旧ID无法直接对应，继续隔离。坐标抽取4,054条记录，按技能/分数/原文去重的听说库1,151条。

这是可追踪的源数据修复，不是对4,054个教学目标或41,402个词义逐条做了独立教学审核。

## 后端读取规则

1. 读取本目录 `curriculum_map.json`。
2. 本次生成的主目标以 `outcome` 和 `generation_contract.task_specific_contract` 为准。
3. 只从 `reviewed_standard_references` 选择教学参考；旧 `gse_candidate_links` 及候选分组列表只保留审计用途。
4. `allowed_usage=resource_or_advanced_reference` 的条目分数在当前阶段之外，不得据此抬高本次任务难度。
5. 无对应的原创目标仍可设计课程，但不可给它伪造标准分数。
6. 必须补齐具体事实、关键意义、可行结果、评分例和独立变体，再通过实际生成器检查，才能开放给用户。
7. 发音/流畅度和听力检查必须有对应音频；无效音频或不确定判断不得更新掌握。
8. 相似目标使用同一证据ID去重，不因为一个任务成功就自动掌握相关目标。

词库和原始PDF依赖相邻的已上传版本目录。旧版本保持原样，新版是单独目录，不能只复制一个JSON后忽略引用路径。

## 查看与复现

- `report.html`：搜索目标、对应决定及前后变化。
- `target_review.csv`：Excel可打开的424条审核结果。
- `target_review.json` / `alignment_review.json`：全部目标与关系决策。
- `review_summary.json` / `verification.json`：范围和实际检查结果。

```bash
python3 research/long-term-map-model-review-2026-10-02/extract_verified_sources.py
python3 research/long-term-map-model-review-2026-10-02/build_review.py
python3 research/long-term-map-model-review-2026-10-02/verify_review.py
python3 research/long-term-map-model-review-2026-10-02/build_report.py
```

原始来源数据、审核决策、生成脚本和结果均保留。审核后状态是 `release_candidate`；公开上线状态仍为false，具体课程、实际评分链路和真实用户证据的门槛未被改成通过。
