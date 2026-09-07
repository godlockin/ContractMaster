# 同类比较：适合谁，借鉴什么

资料核实日期：2026-09-07。依据为源码/指令、官方文档和论文，未做统一部署实测；没有准确率、价格或性能排行榜。“未核实”不等于对方没有。

## 用户选择

| 需求 | 本项目定位 | 当前边界 |
|---|---|---|
| 用文件路径在已有agent中审核 | Skill、本地处理、动态角色及证据输出 | 需Python、模型、宿主工具和脱敏复核 |
| 看清为何提出意见、哪里没审完 | 原文、关系、异议及部分状态 | 法律正确性仍需专业评测 |
| 企业审批、签署、履约管理 | 当前专注合同审查 | 不提供完整CLM |
| 专业Word内修订 | 主要输出Markdown/JSON和离线复核 | 完整红线、版式验收尚有缺口 |
| 托管服务及企业保障 | 可自行检查代码与样例 | 无托管模型、SLA或安全认证承诺 |

## 代表项目

| 对象 / 来源 | 值得借鉴 | 本项目吸收或计划 / 差距 |
|---|---|---|
| [老刘NLP ContractAuditAgent](https://github.com/liuhuanyong/ContractAuditAgent) | 分阶段、规则与模型分工 | 本地处理和契约自行实现，没有复制代码；其串行/Mock路径不能证明实际审核，我们同样区分模拟与真实执行 |
| [hc938456/contract-review](https://github.com/hc938456/contract-review) | 财务/法务/业务分工 | 六基础＋专项、交叉责任、版本门禁；真实全流程效果待验收 |
| [ai-legal-review-skillkit](https://github.com/Xigua9xi/ai-legal-review-skillkit) | 企业偏好、schema、合成评测 | 已有输出契约和开发集，企业playbook治理仍待完善 |
| [iTerms](https://www.iterms.com/) / [MeCheck](https://powerlaw.ai/mecheck) | 企业标准、定位、版本和协同 | 借鉴定位及留痕；本项目没有完整企业流程，未实测双方效果 |
| [Ironclad](https://support.ironcladapp.com/hc/en-us/articles/12275685560215-Ironclad-AI-Playbooks-Overview) / [Spellbook](https://help.spellbook.legal/en/articles/11327030-create-playbooks) | 首选条款、退让底线、审批、精细修改 | 规则治理与修改回归是建设方向；本项目缺成熟规则编辑和Word体验 |
| [LegalOn](https://www.legalontech.com/platform) / [Harvey](https://www.harvey.ai/blog/ai-contract-review-guide) | 专业规则、组织知识、跨文档、证据工作流 | 重视法域事实与证据；没有等同的内容库或服务保障，双方中国法全面覆盖未核实 |
| [Anthropic legal plugin](https://github.com/anthropics/knowledge-work-plugins/tree/main/legal) | 企业规则配置和专项任务 | 参考工作流组织；其README默认美国立场不可直接套中国合同，我们的外国法专项也须核验 |
| [OpenContracts](https://github.com/Open-Source-Legal/OpenContracts) | 坐标、注释关系、人工采纳、可复现检索评测 | 借鉴证据和评测方法；保持轻量skill，不提供完整文档管理平台 |

## 当前价值

在已有agent上补齐处理、分工、证据及交付规则，让使用者逐项确认事实、依据、修改和未决事项。原创样例、原始分析、验证脚本及裁定表可公开检查，用户能够先看证据再决定是否采用。

不把角色数量、测试数量或提示词长度当作法律能力证明。更完整的best practices、局限和优先级见[22个对象研究报告](../research/global-comparison-2026-09-07.md)：17个项目/产品/插件、5项评测资源，非全球穷尽调查。

[返回首页](../README.md) · [Benchmark](BENCHMARK.md)
