# Privacy P2 v6 训练结果

## 结论

本轮以 `Qwen/Qwen3-1.7B` 的本地 4-bit MLX 基座、`v4-step160` adapter 为父产物，执行 160 steps 真实 Metal 训练。候选 adapter 已生成并完成 dev-only 实际脱敏评测；候选保持未升级状态，默认仍为 v4。holdout160 未读取。

指标仅适用于本轮合成 reviewed4 dev 集，不能外推为生产准确率或零泄漏证明。

## 训练与数据

- 训练耗时：674.02 秒；MLX 峰值内存（统一内存）：9.073 GB。
- 训练投影：700 行，其中 658 条 unique message；重复 42 条来自既定 replay 配比，不应称为 700 条独立样本。
- dev：128 行；与训练完整 messages 无交集。
- holdout：160 行，未读取。
- 配比：reviewed4 train 400 + 合法祖先 replay：v6/v3/v2 各 100 条。
- 数据 manifest：`artifacts/privacy/experiments/p2-v6-20260915/data/manifest.json`。
- 配置：`training/privacy/configs/p2-v6-20260915.json`，SHA256 `889c593786d0e3b1dcb297cdaf0265babce7ed91e38605074e0d56cc9cf66acf`。

## 产物与父链

- 父 adapter：`artifacts/privacy/adapters/v4-step160/adapters.safetensors`，SHA256 `d8f0db53ab667732b0974ccd87ae44a8ab9a5d1a3429506188e404334c47d339`。
- 候选 adapter：`artifacts/privacy/experiments/p2-v6-20260915/adapter/adapters.safetensors`，SHA256 `732f4958ccc2ecef5d50283dd7ce91b504385fbf678b791b96d0344dacb4cc50`。
- 基座身份：`mlx-community/Qwen3-1.7B-4bit`，verified-download revision `3b1b1768f8f8cf8351c712464f906e86c2b8269`；实测模型 SHA256 `0e86d9677e5193c…`。
- 冻结 runtime：`artifacts/privacy/experiments/p2-v6-20260915/runtime`，标记为当前短文源码冻结副本，不是历史 156 测试快照。
- 评测证据：`artifacts/privacy/experiments/p2-v6-20260915/evalrun/evaluation-provenance.json`。

## Dev 实际脱敏比较

使用同一冻结 runtime、同一 reviewed4 dev128、temperature 0，分别加载 v4 与候选；输出保留 predictions、redacted_text、阻断状态、preservation 结果及 runtime 起止 hashes。

| 指标 | v4 baseline | P2 candidate |
|---|---:|---:|
| rows | 128 | 128 |
| blocked | 9 | 0 |
| delivered with residual | 25 | 18 |
| preservation failed | 24 | 0 |
| character recall（blocked 计 miss） | 0.8069 | 0.9621 |
| character precision | 0.8449 | 0.9413 |
| clean residual | 13 | 8 |
| attack residual | 12 | 10 |
| attack induced leak pairs | 4 | 2 |

candidate 的 18 条 residual 分为：procurement 谈判底线 8 条、finance 项目边界 8 条、engineering 分隔姓名 2 条。下一轮方向为后置秘密限定、项目边界上下文、分隔姓名恢复；本轮不改 runtime、不改数据、不升候选。

评测记录 `inference_calls=128`（行级），`model_generation_calls=80`（canonical cache 口径）；两者分母不同，不能据此把 dev 行数写成 80。

## 可复跑命令

训练使用冻结脚本。当前配置文件中的 data/model/adapter 路径是相对路径；复跑时必须复制配置到新实验目录，仅修改新的 `adapter_path`，并将 data/model/resume 路径固定为已核验路径。旧 adapter 目录不可覆盖。例如：

```bash
cp training/privacy/configs/p2-v6-20260915.json /tmp/p2-v6-rerun.json
# 编辑 /tmp/p2-v6-rerun.json：仅把 adapter_path 指向全新目录；
# data/model/resume_adapter_file 指向已核验的固定路径。
mkdir -p artifacts/privacy/experiments/p2-v6-rerun-20260915-01/
/Users/chenchen/working/sourcecode/tools/law/contract_review/.venv-privacy/bin/python \
  artifacts/privacy/experiments/p2-v6-20260915/runtime/training/privacy/train.py \
  --config /tmp/p2-v6-rerun.json
```

评测使用 `evalrun` 下冻结 runtime 的 `evaluate_redteam.py`，分别加载 v4 和候选 adapter，输出目录为 `evalrun/baseline-v4` 与 `evalrun/candidate-p2`。本轮 smoke 失败记录亦保留；fresh offline env 的新结果见 `artifacts/privacy/qualification/production-v6/long-real-smoke-v2.result.json`。
