# 本地隐私识别与脱敏生产准入计划

目标是把本地敏感信息识别、可逆脱敏、映射保护和失败阻断做到可审计的生产准入水平。该计划不把合同法律审核自动化，也不宣称模型能独立完成法律判断、实体真实性或企业保密策略决定。

## 阶段与工作量

| 阶段 | 内容 | 估计工作量 | 产出与门槛 |
|---|---|---:|---|
| P0 | 运行器/skill 入口接通、配置实际执行与 release 绑定；最低价、斜杠姓名、行业退步回归 | 有界工程验收通过 | 156 tests/0 skipped 已通过（`/tmp/cr-main-final-frozen.log`）；5 个金额/脱敏门禁已独立验证；8 组生产故障测试已覆盖真实 artifact 字节变更、半提交恢复、DOCX、独立 skill 副本等；历史 fault-injection-special 证据不代表本轮状态；P0 证据不等于生产上线批准 |
| P1 | 规则/模型/本地词典分层，逐出现位置映射，长文本分区与合并 | Luna；0.5–1 天；依赖 P0 | 支持上限写入配置；超限整体阻断；无法定位、输出无 ground、完整性失败均阻断；状态：工程与实际 MLX 长文 smoke 通过 |
| P2 | 独立开发/holdout/行业回归与来源审计 | Luna；0.5–1 天；依赖 P0、sources 新开发集 | holdout 冻结后不可调参；旧/候选同环境；scope 保真和整篇 source 保真分列；状态：160 steps 与 dev128 对比完成，candidate residual18 未准入，默认 v4 保持，holdout 未读 |
| P3 | 宿主出站/插件权限、人工抽样复核、运行手册、告警与回滚 | 用户/管理员 + Luna；0.5 天；依赖 P0/P1 | 宿主层证据证明无外发；人工复核签字；默认适配器不变直到门槛通过；状态：仍待机器级/人工验收；宿主隔离不属于数据质量完成项 |

## 可阻断边界

仓库与运行器可强制：模型和适配器完整性 hash、离线加载、原文仅本地处理、未 ground 输出阻断、输出过长/输入过长阻断、实体无法定位阻断、同 literal 多位置语义冲突阻断、映射权限 600、未批准本地词典阻断、实际 runtime artifact 集合 hash 起止一致性、所有失败状态落盘。

仓库不能替用户控制 AI IDE 上游的网络策略、宿主遥测、系统级剪贴板/屏幕采集、外部插件权限或用户自行复制原文的行为。生产部署必须由管理员在宿主层关闭出站与遥测、审查插件权限、限制日志和备份，并由用户确认本地敏感信息清单。不能把仓库内的离线设置描述成宿主级隔离证明。

依赖缺失、模型不可用、完整性失败、未批准词典或规则覆盖不足时可由用户授权使用 rules fallback；fallback 只表示本地规则演练，不能标记为隐私已合格，也不能静默把原文上传云端。

## P0 具体修复

1. 最低价格：修正贪婪金额匹配，避免从内部最低价跨越到后方公开报价；filter 同时要求“最低价格/最低可接受”等语义与保密 cue，普通金额、年度报价和公开结算标准保留。
2. 斜杠姓名：只在显式姓名字段中接受单字斜杠分隔，并用规范化视图映射回原文逐出现范围；任意模糊姓名不恢复，无法严格定位继续阻断。
3. 行业退步：将已评估的 sector-v3-accepted 退步作为 regression 记录，不称为盲测；sources 提供新的独立开发集后，先冻结训练选择，再看新 holdout。
4. 入口与出站：检查 `contract-review-cn/SKILL.md`、`redact_local.py` 的 auto/local/rules 分支、依赖失败和模型异常路径，确认任何失败不外发原文。
5. 配置与 release：`privacy_config.py` 对未实现的敏感类型、保留规则和业务规则显式拒绝；当前 run 必须绑定输入、policy、mapping、模型/adapter 与 runtime 摘要。

入口诊断结论：当前流程为 `prepare → redact-run → 本地复核 → release`；模型结果进入当前 run，并由 release 绑定 source snapshot、mapping、policy、model、adapter、runtime 摘要。`prepare-change` 支持版本结构配对，模型结果 compare 尚不支持，必须显式标注限制。P0 有界工程验收通过；P1 长文与真实 MLX smoke 通过；P2 已完成 160 steps 与 dev128 对比但 candidate residual18 未准入、默认 v4 保持且 holdout 未读；P3 宿主隔离与人工复核仍未完成。

## 验收门槛

候选不得替换默认 v4，直到：P0/P1 测试全通过且无跳过；训练输入、holdout 输入、采样参数及实际 runtime artifact 集合 hash 全部冻结；开发集候选在 residual、blocked、preservation 三项不劣于旧基线；独立 holdout 与三套行业/条款回归均生成完整 predictions、metrics、progress；scope 保真与整篇 source 保真分列；审计脚本验证行数、摘要、adapter hash、runtime 起止 hash 和目录不可覆盖；人工复核确认脱敏包质量。任一残留、误遮蔽或行业退步只记录证据并阻止推广，不通过调高阻断率掩盖。

本轮完成 P0、P1 及 P2 训练/dev 对比证据收口；candidate residual18 未准入，默认 v4 保持，holdout 未读，模型比较仍不支持。剩余工作依赖 holdout、用户/管理员宿主权限和人工抽样复核；工作量估算属于投入范围，不是交付时间保证。
