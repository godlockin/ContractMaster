# 中国同类项目参考

检索/核实日期：2026-09-07。读取公开 README、Skill、部分代码和许可证；未部署项目、未完成安全审计。以下功能仅按标明的证据层级描述，不将宣传内容视为实测结论。参考方法论，本实现不复制代码。

| 项目与来源 | 核实内容 | 本 skill 借鉴 | 差异和局限 |
|---|---|---|---|
| [ContractAuditAgent](https://github.com/liuhuanyong/ContractAuditAgent) / [main.py](https://github.com/liuhuanyong/ContractAuditAgent/blob/main/src/main.py) | 代码顺序调用 document→clause→risk→benchmark→report；README 描述规则+模型；[MIT](https://github.com/liuhuanyong/ContractAuditAgent/blob/main/LICENSE) | 阶段化输入输出、规则和模型分工 | 是串行流水线；导入失败存在 Mock 回退，不能据此保证真实审核或逐字覆盖 |
| [hc938456/contract-review](https://github.com/hc938456/contract-review) / [SKILL.md](https://github.com/hc938456/contract-review/blob/main/SKILL.md) | Skill 规定财务/法务/业务三维和自适应并行 | 专业背景分工、完整交付 | 仅验证指令，未验证调度；许可证未核实，不复制；本地文件处理不等于云模型接触不到原文 |
| [NOMOREKKK/contract-review-skill](https://github.com/NOMOREKKK/contract-review-skill) / [SKILL.md](https://github.com/NOMOREKKK/contract-review-skill/blob/main/SKILL.md) | 10 步审核、金额/冲突检查、引用、自检和 Word 批注规范；[MIT](https://github.com/NOMOREKKK/contract-review-skill/blob/main/LICENSE) | 分层清单、输出门禁 | 未验证可逆脱敏或字符覆盖实现 |
| [Xigua9xi/ai-legal-review-skillkit](https://github.com/Xigua9xi/ai-legal-review-skillkit) / [中文说明](https://github.com/Xigua9xi/ai-legal-review-skillkit/blob/main/README.zh-CN.md) | 规则、企业偏好、合成合同、taxonomy/schema、敏感内容检查；[MIT](https://github.com/Xigua9xi/ai-legal-review-skillkit/blob/main/LICENSE) | 规则/偏好/输出契约分离、合成评测 | 检查脚本不等于完整 PII 识别或可逆脱敏，未验证并行调度 |
| [xiaodingfeng/contract-review](https://github.com/xiaodingfeng/contract-review) | README 描述上传、AI 预分析、审查点、OnlyOffice、知识检索及受控搜索 | 审查点配置、公开检索与合同数据区分 | Web 平台比 skill 重，本次不引入其服务栈；安全说明未做部署验证 |

设计结论：独立实现本地可逆标记与坐标、人工/可信本地脱敏门禁、六背景专家每角色全文覆盖、跨条款质询、运行时法源核实。公开项目未提供本项目的安全性或法律正确性保证。

评测区分三件事：字符进入处理范围（脚本可证明）、专家审阅记录完整（契约可检验）、风险发现质量（需带金标准合同及法律专业复核）。不得用前两项替代第三项。
