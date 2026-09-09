# ContractMaster

**把合同疑点变成有原文、有理由、有修改方向的复核清单。**

面向中国合同审查的 Codex skill，连接法务、财务、业务、争议、合规及语言逻辑视角，帮助使用者定位需要确认、协商和修改的地方。

**[看完整样例](docs/WALKTHROUGH.md) · [开始使用](docs/GETTING-STARTED.md) · [Benchmark](docs/BENCHMARK.md) · [同类比较](docs/COMPARISON.md)**

## 先看能发现什么

以下来自原创虚构采购合同及已保存的AI试审：

| 合同内容 | 审查意见 | 用户价值 |
|---|---|---|
| 100袋×200元，总价写22,000元，大写和分期却是20,000元 | 金额相差2,000元，需要确认真实成交价 | 签署前对齐付款口径 |
| 最晚9月30日交付，却要求9月25日前完成全部验收 | 期限存在冲突，需结合实际交付时间判断 | 连起来看交付、验收和付款 |
| 质量标准依赖尚未提交、由供应商单方确定的附件 | 需双方确认质量及验收依据 | 明确应补材料和修改动作 |

[样例PDF](contract-review-cn/evals/output/pdf/C01-purchase-sample.pdf) → [原始文字](contract-review-cn/evals/inputs/C01.txt) → [处理后文字](examples/purchase/redacted.txt) → **[审查报告](examples/purchase/REPORT.md)**

报告为历史单agent试审，尚非律师裁定；不会把可履行情形一概判为不可能。

## 一分钟体验

只需Git与Python 3.10+。固定原创TXT演示，无需API Key、PDF依赖或模型调用：

```bash
git clone --branch miao https://github.com/godlockin/ContractMaster.git
cd ContractMaster
python3 demo.py
```

脚本打印本次 `REPORT.md` 路径。实际重做本地提取、脱敏和引文校验，再回放3项历史意见；**不冒充新运行的AI审核**。每次新建输出目录，私有映射留在本地。

## 你会得到什么

- 风险的原文位置、触发条件、影响、修改方向及待确认问题。
- 定义、例外、正文附件、金额期限之间的关系分析。
- 法源核验状态、信息安全问题、专家分工及未完成事项。
- 可保留、驳回、修正AI意见的人类复核材料。

```mermaid
flowchart LR
  A[合同与附件] --> B[本地提取脱敏]
  B --> C[用户核对完整性与脱敏]
  C --> D[动态专家规划]
  D --> E[独立审核 / 关系核查 / 质询 / 回归]
  E --> F[证据与完成状态校验]
  F --> G[报告与人工复核]
```

这是工作流契约；脚本处理数据和门禁，实际模型及专家调用由宿主执行。

## 使用

默认采用[双组独立审核](contract-review-cn/references/dual-team.md)：A组六背景正向审查，B组三背景逆向查漏；独立首审后双向质询。程序验证声明及材料一致性，实际隔离与并行仍需宿主执行证据。

| 输入格式 | 处理方式 |
|---|---|
| Word DOCX、TXT、Markdown | Python标准库直接处理，无额外解析依赖 |
| 文字层PDF | 按需安装pypdf；拒绝安装可继续其他文件 |
| 旧Word DOC、RTF、ODT | 用已有本地软件转换DOCX/TXT |
| 扫描PDF、照片 | 本地OCR并核对，不能仅靠pypdf |

缺少依赖只影响对应输入；未处理文件明确列入报告，不能静默跳过。[按需安装与格式说明](contract-review-cn/references/input-formats.md)

按[安装与环境指南](docs/GETTING-STARTED.md)安装skill，使用自然语言提供路径：

```text
我要审核一下这个合同 ~/Downloads/1234.pdf
```

执行入口与隐私边界见 [SKILL.md](contract-review-cn/SKILL.md)。原文和敏感映射保留本地；真实客户合同完成提取及脱敏复核后才能分发给审核 agent。

建议同时提供我方立场、附件、交易背景和适用地区。你无需选择专家或填写JSON，但需要核对本地提取与脱敏结果、补充必要事实，并决定如何处理最终意见。

## 内容

- **[六个原创样例与完整处理过程](docs/WALKTHROUGH.md)**：否定词、调价、违约金、数据处理、附件和定向负例。
- **[Benchmark属性、证据及未完成项](docs/BENCHMARK.md)**：区分流程验证、历史试审和法律质量。
- **[面向用户的同类比较](docs/COMPARISON.md)**：适合谁、借鉴什么、当前差距。

- [动态专家规划](contract-review-cn/references/expert-planning.md)：基础角色、专项增派、工具就绪、计划版本和交叉复核。
- [深度审核协议](contract-review-cn/references/deep-audit.md)：全文、关系、多轮、法源及未决事项门禁。
- [合成测试集](contract-review-cn/evals/ACCEPTANCE.md)：测试输入、预期项及明确的验收边界。
- [国内外项目比较](research/global-comparison-2026-09-07.md)：可借鉴实践及局限。
- [公开合同试审](research/public-contracts/RUN-REPORT.md)：8份公开PDF、300页的文字层试审记录，65项待人工裁定意见。
- [人类复核页面](research/public-contracts/human-review/index.html)：打开本地HTML填写裁定并导出JSON。

第三方合同原件、提取全文、页面截图及私有映射不随仓库发布；来源和下载脚本保留。需要查看原件或重新校验复核包时，先按 [语料说明](research/public-contracts/README.md) 下载到本地。现有复核页面中的本地原件链接需要这些文件；历史产物的绝对路径可能需要适配本机目录。原创合成样本包含在仓库中。

GitHub显示HTML源码；下载后用浏览器打开即可填写裁定。也可直接浏览[CSV裁定表](research/public-contracts/human-review/adjudication-template.csv)。

## 验证

统一入口：`.venv/bin/python scripts/verify.py`。任何测试跳过均视为失败，合成验收在临时副本执行。CI配置覆盖Python 3.10/3.14，远端运行状态以GitHub Actions为准。生产差距、责任分工及验收标准见[生产能力矩阵](docs/PRODUCTION-READINESS.md)。

Python 3.10+；PDF文字提取需 `pypdf`，示例PDF生成另需 `reportlab` 和中文字体。宿主按其后台执行与日志规则运行：

```bash
.venv/bin/python -m unittest discover -s contract-review-cn/scripts -p 'test_*.py'
.venv/bin/python -m unittest discover -s research/public-contracts/tools -p 'test_*.py'
.venv/bin/python contract-review-cn/evals/run_acceptance.py
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

先按[环境指南](docs/GETTING-STARTED.md)创建 .venv 并安装 requirements-pdf.txt。当前 pypdf 6.18.0 环境中，技能42项、复核包6项、演示及回归12项测试全部通过，无跳过；6个合成案例流程检查通过。公开合同初评和部分独立交叉质询不等于每份合同完成六专家四轮验收；没有律师金标准，不报告法律准确率。结构和覆盖校验不能保证穷尽所有风险或法律法规。

历史开发集14/14个预期项命中，**不是14份合同，也不是法律准确率100%**。高保密场景另需宿主技术隔离或可信本地模型；文件权限和提示词不等于沙箱。
