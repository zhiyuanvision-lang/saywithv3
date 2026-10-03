.PHONY: feedback feedback-close feedback-test
# 导出到本项目 support.md 和 tmp/feedback-inbox，成功后关闭后台工单。
feedback:
	python3 scripts/extract-open-feedback.py --from-tengxun --close
# 保留原有命令，与 feedback 行为一致。
feedback-close:
	python3 scripts/extract-open-feedback.py --from-tengxun --close
feedback-test:
	python3 scripts/extract-open-feedback.py --self-test
