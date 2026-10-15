# 法务交付物与能力边界

交付物按受众分离，均绑定案例、快照、合同版本和审核状态。格式示例放在 `assets/templates/`；运行时 agent 可读取模板并填充，不在多个文件复制同一字段定义。

## 内部风险 memo

包含：范围与材料缺口、我方/对方角色、事实假设、逐项证据、法源核验状态、风险后果、最坏情形、首选/退让/底线、审批人、未决问题、红线升级、提取和脱敏限制。保留全部 findings 与来源，不能只给摘要或“可签”结论。

## 对外提案

单独生成，仅含已授权的条款建议、条件、期限和版本标识。不得混入内部评分、底价、红线、私有合同、隐私策略或企业秘密。系统不自动发信、签约、上传或提交谈判结果。

## Word 修订与签约前检查

能力检查必须先声明：当前运行时是否能生成可审计的 DOCX 修订、是否仅能输出替换文本/差异清单、是否处理格式、批注、修订、签章和嵌入对象。不能声称已有自动 Word 修订能力。若有文档工具，先备份原文件，校验每个修改位置与版本绑定；“接受全部”只能表示得到期望修订文本，“拒绝全部”只能表示回到原文语义，且需保留既有修订策略。位置或语义未验收时退回替换清单，不输出假定已完成的 Word 修订。签约前检查覆盖最终文本、附件、优先级、填空、授权/盖章、签署副本、条件、生效日、通知、审批和未决风险；检查通过也不等于法律签核。

## 履约台账与计算说明

台账每行绑定合同条款和证据，记录事件、责任方、到期日、状态、金额、币种、税费、验收/付款依据、通知和下一步。计算说明保留公式、输入来源、单位、舍入、日期时点、情景和人工复核人；缺输入时输出区间或 `unresolved`，禁止编造数值。

履约日期不得默认按 business day 回拨或套用美国节假日；缺少合同日历和事实时标记 `unresolved`。原创设计借鉴：参考 Anthropic 官方 [review](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/review)、[vendor-agreement-review](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/vendor-agreement-review)、[amendment-history](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/amendment-history)、[renewal-tracker](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/renewal-tracker)；仅作工作流来源，不是法律依据。结构统一使用 `assets/templates/legal-audit.json`，不另维护交付模板。
