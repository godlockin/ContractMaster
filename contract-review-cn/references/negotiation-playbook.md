# 谈判 playbook 与立场控制

本文件把法务风险转成可授权的谈判选项；它不替代[深度审核](deep-audit.md)、法源核实或强制法判断，也不自动代表用户发信。

## 每项风险四格

对每个 `finding_id` 建立：

1. `preferred`：我方首选结果及理由；
2. `fallback`：可接受退让、触发条件和换取事项；
3. `red_line`：底线、红线或必须升级事项；
4. `exception_approval`：`none/pending/approved/rejected`，另记录审批证据、范围和绑定版本。

买方通常优先控制验收、付款条件、知识产权、数据/保密、责任上限、终止和供应商持续履约；卖方通常优先控制范围冻结、付款确定性、责任边界、许可范围、客户配合和暂停/终止权。以上只是起始假设，必须标注 `assumption` 并由用户确认；不得把商业偏好写成法律结论。

## 交换与升级

用户或已核定政策明确“不得接受”的事项，不自动生成放宽该事项的退让方案。`fallback` 应写无可用退让及升级原因；技术改名、匿名化承诺或一般业务批准不自动取消该红线。只有有权政策负责人明确变更适用标准并留存新版本后，才能按新标准重新审查；合法性仍独立核验。

每次退让记录“我方让什么、对方给什么、影响哪条风险、是否改变附件/订单/版本、谁批准”。强制法、监管要求、主体资格和不可放弃义务不能作为普通筹码；发现红线仍完成全文审核并升级。未知立场时给买方/卖方两列方案，不臆测客户偏好。

## 版本绑定与中立性

台账使用 `case_id`、`snapshot_digest`、`input_digest`、`playbook_version` 关联本轮；文档节点记录实际版本。案例快照编号、比较摘要、创建时间及授权来源保留在案例索引和内部 memo。正式字段见[台账数据契约](legal-audit-schema.md)。版本变化后，旧方案只能作为历史记录，须重新检查受影响风险；不能用文件名或修改时间认定法律效力。

若计划包含中立审查，显式列出角色、输入和独立输出；未配置则标记 `neutral_review: not_configured`。本文件本身不是中立意见，也不宣称已有 Word 修订、谈判代理或发送能力。

## 建议输出

内部 memo 分离：风险事实、法律/文本依据、商业影响、首选/退让/底线、待授权问题。对外提案只放经授权的条款语言和条件，不泄露内部底价、评分、红线或推理记录。任何提案发送、签署、上传仍由用户在具备授权后执行。

台账仅纳入当前立场适用的规则（或中立规则），买卖双方备选分析另存 memo。字段须符合 `scripts/legal_audit.py`：`id`、`side`、`preferred`、`fallback`、`red_line`、`approval_role`、`exception_allowed`（默认 false）。允许例外不等于已经批准；批准记录须绑定当前政策版本、快照、范围与证据。其余内部字段放在 memo 中。原创设计借鉴：参考 Anthropic 官方 [review](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/review)、[vendor-agreement-review](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/vendor-agreement-review)、[amendment-history](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/amendment-history)、[renewal-tracker](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/renewal-tracker)；仅作工作流来源，不是法律依据；字段和安全边界为本项目原创设计。
