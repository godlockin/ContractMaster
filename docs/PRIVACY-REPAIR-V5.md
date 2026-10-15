# Privacy repair-v5 evaluation record

本轮候选 `artifacts/privacy/adapters/repair-v5` 未替换默认适配器 `v4-step160`，也未通过推广验收。最终 r4 评估使用同一冻结运行器；每个 r4 `metrics.json` 均记录 runtime 文件起止 SHA256，`runtime_code_changed=false`。r1/r2/r3 是修复迭代过程结果，不能当作最终冻结证据。

候选训练证据：900 条训练样本（600 新样本、300 回放）、180 条开发样本；160 steps，实际 532.6 秒（约 8.9 分钟），峰值 8.624 GB，adapter 3,676,917 bytes，状态 `TRAINED_NOT_YET_QUALIFIED`。adapter SHA256 为 `ebf8764e07e39150ca7507bcc5231656afa3e93c0bafdc2f47e7864f1b736c5e`，父适配器 SHA256 为 `d8f0db53ab667732b0974ccd87ae44a8ab9a5d1a3429506188e404334c47d339`。训练配置见 [repair-v5.json](../training/privacy/configs/repair-v5.json)，数据来源见 [repair-v5-mixed manifest](../artifacts/privacy/data/repair-v5-mixed/manifest.json)。

## Runtime 修复

- 普通合同、订单、运单、批次、条款编号不会因模型误标 `PROJECT` 而遮蔽；显式内部课题、内部研发代号仍识别为 `PROJECT`。
- 同一 literal 出现在交易编号字段和项目字段时，出现位置语义冲突，阻断并返回 `AMBIGUOUS_ENTITY_OCCURRENCE`。
- 模型输出去掉斜杠的姓名，仅在显式“姓名/登记姓名”字段且每个汉字由斜杠分隔时可逆恢复；其它无法定位的模型项继续以 `MODEL_ITEMS_UNGROUNDED` 阻断。

## 开发集

180 条 clean 开发样本：旧模型 blocked=0、residual=8、preservation_failed=12；新模型 blocked=1、residual=7、preservation_failed=0。新模型 precision=0.943551，旧模型 precision=0.921011。开发样本不含 attack 行，不能据此计算 paired attack 指标。

## 独立 holdout

140 行（70 clean、70 attack）：旧模型 blocked=9、residual=16；新模型 blocked=2、residual=14。按 scoring scope 的 preservation_failed 均为 0，但独立整篇来源复核显示 preserve_payload 负例全文逐字保留：旧 35/40，新 23/40。新模型 17 条全文差异均为虚构负例标签被识别为 SECRET/PROJECT；业务条款仍逐字保留。该差异不能被 scope 指标隐藏。

攻击子集严格分母为 50（排除 20 条负例）：旧 37 无残留、11 残留、2 阻断；新 39 无残留、10 残留、1 阻断。

## 历史回归

冻结结果目录均保留旧/新预测、metrics、progress：

- `artifacts/privacy/evals/matrix-v3-old-v5-r4` / `matrix-v3-new-v5-r4`（1140 行）
- `artifacts/privacy/evals/matrix-v3-clauses-old-v5-r4` / `matrix-v3-clauses-new-v5-r4`（190 行）
- `artifacts/privacy/evals/sector-v3-accepted-old-v5-r4` / `sector-v3-accepted-new-v5-r4`（36 行）

matrix-v3 attack 行中旧残留 114、新残留 100；旧阻断 119、新阻断 83。该结果显示候选有所改善，但仍有大量残留，不能推广。开发集共同漏检集中在“内部最低价格/年度报价”语义：下一轮需同时修复贪婪匹配和“最低价格”保密 cue，不能据此轮盲测改动。

| 数据集 | 攻击行 | 当前旧 runtime：残留/阻断/保真失败 | 当前新 adapter：残留/阻断/保真失败 |
|---|---:|---:|---:|
| matrix-v3 | 570 | 114 / 119 / 0 | 100 / 83 / 0 |
| matrix-v3-clauses | 95 | 26 / 7 / 0 | 15 / 12 / 0 |
| sector-v3-accepted | 18 | 0 / 1 / 0 | 3 / 0 / 0 |

sector-v3-accepted 是明确退步：新 adapter 将旧模型的 0 条攻击残留变为 3 条。该独立行业场景退步，加上 matrix-v3 仍有 100 条攻击残留，是不推广理由。历史旧结果还存在原始旧 runtime 与当前旧 runtime 的差异；本表只报告最终 r4 同 runtime 的公平对照，不能把当前旧 runtime 结果倒推为原始旧 runtime 的改进来源。

完整工程验证：`scripts/verify.py` 135 tests、0 skipped，流程检查与 score_review 均通过。最终审计脚本为 [audit_repair_v5.py](../training/privacy/audit_repair_v5.py)，其独立审计产物见 [final-audit.json](../artifacts/privacy/qualification/repair-v5/final-audit.json)、[source-independent-audit.json](../artifacts/privacy/qualification/repair-v5/source-independent-audit.json)。证据一致性主验收已通过（完整 3372 条输入对照、runtime/hash/指标一致）；这不等于模型推广验收通过，也不代表法律质量或零残留。
