# 隐私生产 v6 状态

`reviewed4` 是依据审核通过的 v3 模板规格生成的有界合成研发集，共 24 个模板骨架、688 行（train 400、dev 128、holdout 160）。这些数据不代表 688 个独立业务模板，也不代表生产场景覆盖度。

生成器逐一消费 spec 的 positive/negative 正文，按语义类型生成 gold span，保留普通业务金额，生成 clean/attack 成对样本及 MLX train/dev 投影。独立 validator 已通过 spec、pair/gold/preserve、MLX，以及 v6、v3、v2、repair-v5 四个祖先训练文件审计；范围和哈希见 `artifacts/privacy/data/reviewed4/audit.json`。

本轮没有新增训练，默认 v4 未改变。reviewed1、reviewed2、reviewed3 历史产物仍为拒绝状态。

主审最终冻结验证为 156 tests、0 skipped PASS（`/tmp/cr-main-final-frozen.log`），包含精确金额重构错误码、timeout 错误码和 8 组生产故障测试。P0 有界工程验收通过，不等于完整生产准入；宿主出站、插件权限、人工抽样和长文/模型比较仍未完成。

P2 计划：使用 train 400 加合法祖先 replay，dev 用于调参，holdout 160 冻结候选后再查看。训练准入仍依赖 P0 故障测试及后续数据质量门槛。
