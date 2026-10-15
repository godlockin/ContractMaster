# 合同法务全生命周期路由

本参考用于在逐段审核之外识别交易阶段、授权边界和交付动作。它补充[可执行 workflow](workflow.md)、[案例目录管理](case-management.md)及[隐私门禁](privacy.md)，不复制其输入、版本和脱敏字段。

## 受理门禁与路由

先建立本地 case、合同组和版本关系，再记录：委托人、我方主体及角色、审核目的、期望日期、已知签署/履行状态、适用法域、行业监管假设、授权人、禁止动作、完整材料清单。缺少关键事实时，继续审核不依赖该缺口的部分；不得宣称全审完成，标记 `unresolved` 并说明受限范围。

按阶段路由：

| 阶段 | 必查重点 | 输出重点 |
|---|---|---|
| 受理/立项 | 授权、利益冲突提示、主体与角色、材料完整性 | 受理记录、缺件清单、假设 |
| 谈判/草拟 | 我方立场、风险排序、版本来源、变更影响 | 内部风险 memo、谈判提案 |
| 签署前 | 最终文本、附件、签字权限、盖章/电子签、法源时点 | 签约前检查表、未决升级 |
| 签署/生效 | 签署副本、签署时间、条件、通知、文本优先级 | 签署证据索引、生效判断 |
| 履行/变更 | 交付、验收、付款、通知、豁免、补充协议、订单 | 履约台账、变更审核 |
| 争议/终止 | 违约事实、证据保全、通知、时效与管辖约定、终止后义务 | 争议事实矩阵、止损建议 |
| 归档/复盘 | 完整签署包、权限、保留期、历史链 | 归档清单、未决转交 |

## 立场、法域与时点

分别记录 `我方立场`、`对方立场`、`中立审查假设`。未配置中立审查角色时不得假定已经中立复核；可并列给出双方后果。默认中国大陆语境只表示初始路由，不替代主体、交易地、履行地、行业和约定法域核实；不自动引入美国律师保密特权或法定节假日推算。

法源结论记录来源、发布日期、施行/废止或修订状态、检查日、适用主体及合同相关日期。优先官方来源：国家法律法规数据库（https://flk.npc.gov.cn/）、全国人大（https://www.npc.gov.cn/）、最高人民法院（https://www.court.gov.cn/）、中国政府网（https://www.gov.cn/）。无法在线核实则写 `unverified`，不要填写猜测条号。

## 签署、履行、争议、交付

签署前不得把“版本最新”推导成“可签”；检查授权、最终附件、填空、空白条款、签章方式和条件。履行中按合同义务建立事件、证据、金额和责任人台账；计算保留公式、输入、币种、税费和假设，不能用模型自检代替业务核对。发生争议时按用户委托范围审核；缺件或范围外部分标记未审和影响，不把有限审核写成全审。红线单独升级，但商业谈判方案不得压过强制性法律要求。

禁止未经授权自动签约、发信、上传或代表用户作实质法律行为。用户明确授权的本地操作可执行，但仍保留版本、证据和失败记录。向云 agent 提供的只能是脱敏公开包；私有合同、隐私策略、企业秘密和底价不上传。

原创设计借鉴：参考 Anthropic 官方 [review](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/review)、[vendor-agreement-review](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/vendor-agreement-review)、[amendment-history](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/amendment-history)、[renewal-tracker](https://github.com/anthropics/claude-for-legal/tree/main/commercial-legal/skills/renewal-tracker)；仅作工作流来源，不是法律依据。本文件为本项目原创路由，未复制代码或未核实法条。

## 本地工具示例

以下是 skill 入口目录下 `scripts/legal_audit.py` 的本地离线入口。先将 `SKILL_DIR` 设为本 skill 安装目录；输入文件仅在本机读取，输出目录必须是新目录。返回码 `0` 仅表示 ledger 声明结构就绪，`2` 表示部分/未决，`1` 表示输入或输出操作无效；三者都不是法律签核：

```bash
SKILL_DIR=/已安装/contract-review-cn
python3 "$SKILL_DIR/scripts/legal_audit.py" init --output /本地私有/C001-audit.json
python3 "$SKILL_DIR/scripts/legal_audit.py" check --input /本地私有/C001-audit.json --output /本地私有/check-01
python3 "$SKILL_DIR/scripts/legal_audit.py" report --input /本地私有/C001-audit.json --output /本地私有/report-01
```

`check` 或 `report` 返回 `PARTIAL` 时不能改名为完整审核；先补材料/事实/专家输出，再以新输出目录重跑。主体签署证据、生效条件或 `effective_date` 未证实时，必须保持 `PARTIAL`，不能推出“可签”。`report` 只生成私有本地状态报告；对外使用仍须经过 workflow 的脱敏、release 和人工复核。
