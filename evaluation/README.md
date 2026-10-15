# 隐私识别独立测评

本目录保存本地隐私识别模型历史评估。已实测数据是 `datasets/reviewed4-dev128/dev.jsonl` 的 128 条开发集；不含 holdout，也不作为独立盲测或生产资格证明。模型权重不复制，推理由外部 runner 完成，本目录只离线评分。

正式报告：

|版本|样本|residual|blocked|preservation failed|recall|precision|报告|
|---|---:|---:|---:|---:|---:|---:|---|
|baseline-v4|128|25|9|24|0.806872|0.844913|[报告](reports/baseline-v4.json)|
|candidate-p2|128|18|0|0|0.962085|0.941267|[报告](reports/candidate-p2.json)|

只需 Python 3.10 及以上版本，无第三方依赖。可将整个 `evaluation/` 复制到任意目录，在它的新父目录运行以下命令；不需要复制训练项目。输出文件已存在时会拒绝覆盖，请更换输出路径。

```bash
python -m evaluation.cli --data evaluation/datasets/reviewed4-dev128/dev.jsonl --predictions evaluation/models/baseline-v4/predictions.jsonl --manifest evaluation/models/baseline-v4/core-manifest.json --output /tmp/baseline-v4-report.json
python -m evaluation.cli --data evaluation/datasets/reviewed4-dev128/dev.jsonl --predictions evaluation/models/candidate-p2/predictions.jsonl --manifest evaluation/models/candidate-p2/core-manifest.json --output /tmp/candidate-p2-report.json
python -m unittest discover -s evaluation -t .
```

合同细微修改挑战集真实存在于 `datasets/contract-changes-v1/`，共 28 对，状态为 `challenge_only_unreviewed`，未律师复核、未跑模型。验证与评分命令（score 输出目录，不是 JSON 文件）：

```bash
PYTHONPATH=. python -m evaluation.contract_changes validate-data --data evaluation/datasets/contract-changes-v1/changes.jsonl --manifest evaluation/datasets/contract-changes-v1/manifest.json
python -m evaluation.contract_changes score --data evaluation/datasets/contract-changes-v1/changes.jsonl --predictions /path/to/your/predictions.jsonl --model-manifest /path/to/your/model-manifest.json --output /tmp/contract-changes-score
```

将 `/path/to/your/` 替换为实际路径；模型清单必须对应生成这批预测的模型版本。合同预测每行格式为 `{"id":"CCV1-001","risk_codes":["economic_total"]}`，必须包含全部 28 个样本；无实质变化用空数组。评分只检查风险标签匹配，不评判法律解释质量。

隐私新预测可用 `{"id":"row-1","blocked":false,"predicted_spans":[{"start":3,"end":7}]}`。坐标为原文字符下标，左闭右开；此模式验证定位覆盖，不证明脱敏输出安全。阻断单列统计。历史模式只校验和汇总已有计数，不重建缺失的定位证据。

接入新版本时，新增模型目录、保存原始预测、按现有清单结构填写真实基座和适配器摘要，再计算数据与预测文件 SHA-256，并输出到新的报告文件。归档身份记录不等于本次重新加载权重。开发集原始行内历史 `train_allowed` 不作为本项目训练许可；本项目按外层清单禁止用该开发集训练。

目录约定：`datasets/` 含数据及 manifest，`models/` 含无权重预测与模型身份，`evidence/` 含来源与运行时证据，`reports/` 含 core CLI 结果。manifest 必须绑定 model_id、base_repo、base_revision、base_weights_sha256、adapter_sha256、runtime_sha256、dataset_id、dataset_role、protocol、dataset_sha256、predictions_sha256。历史 predictions 是 `legacy-counts-v1`，缺少逐出现 span，不能冒充 native-span-v1；新模型由外部 runner 生成预测后再评分。适用范围是本地隐私识别与脱敏 Skills，不是合同法律审核综合合格证；当前剩余泄露 18 项，candidate 不具备生产准入。
