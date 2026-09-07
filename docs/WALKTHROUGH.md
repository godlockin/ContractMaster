# 从合同到可行动的意见

本页使用原创虚构样例，可随项目查看。报告为已保存的单agent试审，法源尚未全面核验。

## 输入 → 处理 → 分析 → 报告

1. **合同输入**：[PDF](../contract-review-cn/evals/output/pdf/C01-purchase-sample.pdf) / [TXT](../contract-review-cn/evals/inputs/C01.txt)。故意设计金额、日期及质量附件问题；不是真实客户合同。
2. **本地处理**：[脱敏全文](../examples/purchase/redacted.txt) / [公共包](../contract-review-cn/evals/results/bundles/C01.json) / [处理指标](../examples/purchase/summary.json)。实际生成9片段、420个脱敏后字符、2处实体标记；保留审查所需金额、日期与条件。映射保留本地。
3. **关系分析**：数量×单价→总价→大写→分期；交付→到货→验收；正文引用→附件缺失→质量标准→救济。
4. **审查输出**：**[完整报告](../examples/purchase/REPORT.md)**，含3项历史意见、8段引文及建议。

例如，9月25日验收早于最晚9月30日交付，需要协调期限；提前交货仍可能满足要求，所以不能断言所有履行情形都不可能。这种条件化分析比只给一个“高风险”标签更便于业务确认。

`python3 demo.py` 重做本地处理和引文校验，再回放历史报告，不调用模型、不生成虚假专家记录。字符可重组不等于语义理解正确，脱敏后坐标也不等于原文字节坐标。

## 更多原创样例

| 案例 | 原始合同 | 审核主题 |
|---|---|---|
| C01 采购 | [TXT](../contract-review-cn/evals/inputs/C01.txt) | 金额、期限、附件 |
| C02 维护服务 | [TXT](../contract-review-cn/evals/inputs/C02.txt) | 无需/应、双重否定、调价例外 |
| C03 违约金 | [TXT](../contract-review-cn/evals/inputs/C03.txt) | 区分合同价与损失，不机械套用比例阈值 |
| C04 定向负例 | [TXT](../contract-review-cn/evals/inputs/C04.txt) | 不误报一致金额和已有保密例外 |
| C05 数据处理 | [TXT](../contract-review-cn/evals/inputs/C05.txt) | 目的限制、终止后用途、脱敏和恶意指令 |
| C06 正文附录 | [TXT](../contract-review-cn/evals/inputs/C06.txt) | 工作日/自然日、优先级、缺失引用 |

**[六案例完整分析](../contract-review-cn/evals/results/blind-review.md)** · [预期项及禁止误判标签](../contract-review-cn/evals/oracle/manifest.json)

## 大合同的交叉质询

公开工程模板首轮9项意见，第二agent结合上下文给出3项支持、6项部分支持，指出部分意见忽略已有救济、应降为配置提醒。原记录和反证并列保留，最终由人判断。

[首轮分析](../research/public-contracts/reviews/batch-construction.json) · [反证及修正](../research/public-contracts/cross-review/P04.json) · [CSV裁定](../research/public-contracts/human-review/adjudication-template.csv)

这展示实际交叉复核怎样纠正初评，不是更多agent必然更准的证明。第三方原件需按[来源说明](../research/public-contracts/README.md)下载；原创样例已完整随项目提供。

[返回首页](../README.md)
