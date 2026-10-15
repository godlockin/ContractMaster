# 主合同、补充协议与订单链

本参考用于处理主合同、补充协议、订单、确认单、附件和终止文件的关系。它补充[修改审核流程](change-review.md)与案例版本索引；不重复维护版本字段。

## 先建链，再判冲突

为每份文件登记稳定文件身份、版本/草稿状态、前序文件、签署状态、签署时间、签署/授权证据、生效条件、`effective_date`、终止/失效时间、适用范围及优先关系来源。优先关系必须来自文本或用户确认；不能按文件名、创建时间、页数或“文件更新”猜测。

默认只提出待核实链：主合同 → 补充协议 → 订单/确认单 → 履行记录。某些交易可能约定订单优先、补充协议仅修改指定条款，或后文整体替代前文；必须引用原文并说明范围、冲突条款和未决事实。

## 状态与效力

运行时 `scripts/legal_audit.py` 当前只接受 `draft`、`signed`、`effective`、`terminated` 四种 `document_chain.status`。`approved_for_signature`、`suspended`、`expired`、`unknown` 只能作为 memo 的 `known_gaps`/证据说明，不能写入该字段；若需正式状态扩展，必须先升级工具契约。草稿不是签署；签署副本也不必然已生效；生效不等于已履行。`effective` 必须有 `effective_date` 和签署/授权证据；缺少任一项保持 `PARTIAL`，不能输出可签结论。不能因文件更“新”推断法律有效。

## 逐项审查

对每一修改：定位主条款与修改文件，核对定义、金额、期限、责任、附件、通知、争议解决、优先级和终止后存续；同时检查删除、替换、范围扩张和未随之更新的交叉引用。主合同与订单冲突时并列两种解释，要求用户确认交易事实和授权，不擅自选有利解释。

## 终止与归档

终止文件应说明依据、通知、日期、未履行义务、付款/交付、数据返还、保密、知识产权和争议条款存续。归档保存完整签署包、附件、订单、通知和证据索引；历史版本只读，新的补充协议建立新链节点。链完整性不是法律意见，也不替代当地律师或授权负责人的签核。

履行日期按合同明文、证据和用户提供的日历判断；不默认回拨工作日，也不引入美国节假日。原创设计借鉴：参考 Anthropic 官方 [review](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/review)、[vendor-agreement-review](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/vendor-agreement-review)、[amendment-history](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/amendment-history)、[renewal-tracker](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/renewal-tracker)；仅作工作流来源，不是法律依据；本文件为本项目原创审查路由。
