# ContractMaster

面向中国合同审查的 Codex skill：本地提取与脱敏、动态专家规划、多背景交叉审核、原文证据定位及人工复核。

## 使用

将 `contract-review-cn/` 安装到本机 Codex skills 目录，使用自然语言提供合同路径：

```text
我要审核一下这个合同 ~/Downloads/1234.pdf
```

执行入口与隐私边界见 [SKILL.md](contract-review-cn/SKILL.md)。原文和敏感映射保留本地；真实客户合同完成提取及脱敏复核后才能分发给审核 agent。

## 内容

- [动态专家规划](contract-review-cn/references/expert-planning.md)：基础角色、专项增派、工具就绪、计划版本和交叉复核。
- [深度审核协议](contract-review-cn/references/deep-audit.md)：全文、关系、多轮、法源及未决事项门禁。
- [合成测试集](contract-review-cn/evals/ACCEPTANCE.md)：测试输入、预期项及明确的验收边界。
- [国内外项目比较](research/global-comparison-2026-09-07.md)：可借鉴实践及局限。
- [公开合同试审](research/public-contracts/RUN-REPORT.md)：8份公开PDF、300页的文字层试审记录，65项待人工裁定意见。
- [人类复核页面](research/public-contracts/human-review/index.html)：打开本地HTML填写裁定并导出JSON。

第三方合同原件、提取全文、页面截图及私有映射不随仓库发布；来源和下载脚本保留。需要查看原件或重新校验复核包时，先按 [语料说明](research/public-contracts/README.md) 下载到本地。现有复核页面中的本地原件链接需要这些文件；历史产物的绝对路径可能需要适配本机目录。原创合成样本包含在仓库中。

## 验证

Python 3.10+；PDF文字提取需 `pypdf`，示例PDF生成另需 `reportlab` 和中文字体。宿主按其后台执行与日志规则运行：

```bash
python3 -m unittest discover -s contract-review-cn/scripts -p 'test_*.py'
python3 -m unittest discover -s research/public-contracts/tools -p 'test_*.py'
python3 contract-review-cn/evals/run_acceptance.py
```

当前技能29项测试、复核包6项测试及6个合成案例流程检查通过。公开合同初评和部分独立交叉质询不等于每份合同完成六专家四轮验收；没有律师金标准，不报告法律准确率。结构和覆盖校验不能保证穷尽所有风险或法律法规。
