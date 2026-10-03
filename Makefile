.PHONY: feedback feedback-close feedback-test
# 导出到本项目 support.md 和 tmp/feedback-inbox；不改变后台工单状态。
feedback:
	python3 scripts/extract-open-feedback.py --from-tengxun
# 明确需要处理完导出批次时使用。
feedback-close:
	python3 scripts/extract-open-feedback.py --from-tengxun --close
feedback-test:
	python3 scripts/extract-open-feedback.py --self-test
