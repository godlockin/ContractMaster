# Benchmark attributes 与当前结果

更新：2026-09-07。工程验证、历史试审与法律质量分别展示；没有律师金标准，不提供法律准确率排名。

| 属性 | 定义 / 度量 | 当前证据 | 尚不能证明 |
|---|---|---|---|
| 场景覆盖 | 数量、领域、语言、法域、长度、格式 | 6个原创案例；另8个公开PDF/300页，中文和英文，技术文件含8类模板 | 所有合同及法域覆盖 |
| 提取完整性 | 页数、空页、图像、表格/公式及原页一致性 | 文字层提取和缺口记录，部分视觉抽查 | 300页全部版面验收或OCR准确率 |
| 字符覆盖 | 无间隙重组、坐标和原文匹配 | 合成流程及深度门禁测试，采购demo9片段可重组 | 模型逐字理解正确 |
| 脱敏边界 | 已知敏感值移除、可逆映射、发布门禁 | 已知实体及JSON转义回归检查通过 | 开放集PII零漏检、OS隔离 |
| 风险发现 | 预期项命中、漏报、额外发现裁定 | 历史单agent开发集14/14预期项命中，AI临时标签 | 法律准确率100%或真实合同召回率 |
| 误判控制 | 禁止项、定向负例、执行级行为 | 历史14项通过、0失败、1未评估 | 未评估的注入执行项已通过 |
| 证据可追溯 | 输入摘要、引文、坐标 | 开发集30段引文；公开65项意见引文经核对 | 引用真实即论证成立 |
| 上下文推理 | 定义、例外、引用、附件、多跳关系 | 合成关系案例、工程9项定向质询 | 已有独立多跳准确率 |
| 法源质量 | 来源、条号、有效版本、适用事实 | 未核验状态门禁；部分公开试审依据核验 | 全部发现已完成法律核验 |
| 动态专家 | 专项角色、角度责任、四轮和计划版本 | 技能29项测试、独立CLI复测 | 真实六专家四轮已全面验收 |
| 修改质量 | 消除原问题、不引入新冲突、交易可接受性 | 保存修改建议供人工判断 | 已有独立评分或完整Word红线验收 |
| 人工可审阅性 | 原件、意见、反证、裁定及导出 | 65项页面实测导出、6项工具测试 | AI质询等于律师裁定 |
| 资源成本 | 模型、token、延迟、费用、重试 | 离线demo模型调用为0；真实审核暂无统一数据 | 提效百分比、模型性价比排名 |

## A. 工程验证

技能29项测试、复核包6项测试、6个合成案例确定性流程检查。测试数不是质量排名。运行：

另有离线演示3项测试：历史回放及拒绝覆盖、输入变更拒绝、历史报告变更拒绝；已验证迁移到新目录后运行。此项属于工程可复现性，不新增法律试审成绩。

```bash
python3 -m unittest discover -s contract-review-cn/scripts -p 'test_*.py'
python3 -m unittest discover -s research/public-contracts/tools -p 'test_*.py'
python3 contract-review-cn/evals/run_acceptance.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

[测试说明](../contract-review-cn/evals/ACCEPTANCE.md) · [流程结果](../contract-review-cn/evals/results/pipeline-acceptance.json)

## B. 历史合成开发集

一次单agent提交，模型元数据 `unknown`，AI裁定临时标签。14项命中、30段引文；precision为空，法源全面核验未完成，严重性未评分，六专家端到端未运行。

[机器可读结果](../contract-review-cn/evals/results/evaluation.json) · [预期项](../contract-review-cn/evals/oracle/manifest.json) · [原始试审](../contract-review-cn/evals/results/blind-review.json)

14/14是预期问题数量，不是合同份数，更不是法律准确率。

## C. 公开模板探索性试审

8个PDF、300页、65项待人工裁定意见。技术汇编分两批累计读完104页；工程合同9项另经第二agent质询，支持3项、部分支持6项。

[运行说明](../research/public-contracts/RUN-REPORT.md) · [引文与哈希校验](../research/public-contracts/human-review/validation.json) · [浏览器导出验证](../research/public-contracts/human-review/ui-validation.json)

这是文字层试审与部分定向交叉，不是每份合同六专家四轮完整验收。没有人类标签，暂不报告precision/recall。

## 下一轮如何评价

冻结文档、模型、提示、立场与计划；开发集和留出集隔离。两名专业人员独立标注并仲裁，同时标注AI遗漏。分别报告高风险漏报、误报、事实/法源错误、引用、严重性、修改质量、部分审核比例、成本及耗时。

同条件比较单角色、六角色一轮、六角色四轮；未经对照不宣称多agent优于单agent。CUAD、ContractNLI、ACORD分别测抽取、推断或检索，不能拼成中国合同审核总准确率。[公开基准来源](../research/global-comparison-2026-09-07.md)

[返回首页](../README.md)
