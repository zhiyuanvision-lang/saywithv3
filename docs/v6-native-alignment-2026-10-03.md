# v6 原生界面对齐记录

依据：[App 学习流程与界面设计 v6](/Users/lhy/Workspace/SayWithV3/docs/v6-app-learning-stage.md)。

## 已调整

- 首页只展示今日复习和继续学习；已学内容在进展页。首页标题为可缩放的 26 pt。
- 学习页将对方原话和重点表达放入两个自然高度的卡片，中文含义和音频紧随表达。
- 引导、独立和复习页使用连续对话，角色名在气泡外，用户消息右对齐；只展示真实发生的对话。
- 顶部只保留任务标题、进度和自己的时间；详细条件按需打开。喇叭旁是翻译图标。
- 底部保留一个全宽录音主按钮，提示和文字练习为次要入口；处理中禁止重复发送。
- 反馈按结果、证据、下一步展示；证据不足时不宣布任务成功或已掌握。
- 全局可拖动意见反馈入口覆盖页面与弹窗，支持图片、草稿、历史、回复和结束工单。

## 原生截图

以下截图来自 iPhone 17 模拟器的实际 App。课程为测试数据，结果不能用于证明真实学习效果。设计稿的示例对话不会预填成用户答案。

### 首页

![首页](/Users/lhy/Workspace/SayWithV3/docs/assets/v6-app-home.png)

### 到期复习首页

![到期复习首页](/Users/lhy/Workspace/SayWithV3/docs/assets/v6-app-home-review.png)

### 学习

![学习](/Users/lhy/Workspace/SayWithV3/docs/assets/v6-app-learning.png)

### 引导练习

![引导练习](/Users/lhy/Workspace/SayWithV3/docs/assets/v6-app-guided.png)

### 独立应用

![独立应用](/Users/lhy/Workspace/SayWithV3/docs/assets/v6-app-independent.png)

### 任务反馈

![任务反馈](/Users/lhy/Workspace/SayWithV3/docs/assets/v6-app-feedback.png)

### 复习

![复习](/Users/lhy/Workspace/SayWithV3/docs/assets/v6-app-review.png)

### 复习结果

![复习结果](/Users/lhy/Workspace/SayWithV3/docs/assets/v6-app-review-result.png)

### 意见反馈

![意见反馈](/Users/lhy/Workspace/SayWithV3/docs/assets/v6-app-opinion-feedback.png)

## 验证与范围

Python 后端：50 项测试及 4 个子测试通过。模拟器验证学习、三轮引导、独立应用、反馈、直接复习，以及跨页面和设置弹窗的反馈入口；深色模式、最大辅助字号与减少动态效果下也完成流程检查。

iPhone 12 Pro Max 已安装并启动 1.0.6 (599)，连接腾讯云后端。真人录音效果和完整 VoiceOver 操作仍需人工验收。

开发测试工单 `5bb35262b72757948233320d170d4af9` 已通过原后台接口确认包含文字、1 张图片和追加回复，可在[原项目反馈后台](https://www.zhiyuanv.com/admin/product/saywith/section-feedback)查看；浏览器未登录管理员，因此此项验证使用后台接口。

真实课程生成有质量门槛；未通过内容或语音检查的课程保留为 `needs_review`，不发布。详见 [验证记录](/Users/lhy/Workspace/SayWithV3/verification/feedback-ui-2026-10-03.json)。
