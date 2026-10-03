课程地图与资源模块

用途：统一读取和校验目前已完成的地图，导出保留相对依赖的本地快照。
版本：1.0.1-model-reviewed；140个分组，424个具体目标，41402条词义。
运行时读取模块仅依赖Python 3.10及以上的标准库。

从项目根目录运行：
  python -m modules.curriculum validate
  python -m modules.curriculum target ARRANGE.A2.s2
  python -m modules.curriculum senses "time" --limit 5
  python -m modules.curriculum export --output releases/curriculum/1.0.1-model-reviewed
  python -m modules.curriculum verify-release releases/curriculum/1.0.1-model-reviewed

导出目录包含当前模型审核版及两个相邻依赖目录，保留研究脚本、标准PDF、
原始词库JSON和SQLite。已生成的旧ZIP和缓存不再重复打包。
输出目录必须尚不存在；发现同名目录不覆盖。导出末尾生成SHA-256清单。
此快照在本地保存；未上传、公开发布或改变原始资料许可。

研究构建入口仍在原目录，保留可追溯历史，不移动已有文件：
  research/long-term-map-model-review-2026-10-02/extract_verified_sources.py
  research/long-term-map-model-review-2026-10-02/build_review.py
  research/long-term-map-model-review-2026-10-02/verify_review.py
执行以上三个脚本可以重新编译当前审核版（依赖PyMuPDF与jsonschema）。
建议在导出快照副本执行；当前运行数据通过仓库接口只读访问。

get_target仅提供已审核目标合同和采纳参考，不返回旧候选作为生成依据。
query_senses返回候选，保留未分级和星号来源状态；主题、语境和教学审核
由下一模块完成。默认成人使用GL、SSGL，不能把候选检索当作适配审核。
公开课程仍需具体任务、模型及声音、评价链路和真实效果的相应检查。
