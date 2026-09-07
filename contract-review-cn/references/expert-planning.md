# 动态专家规划与初始化

在 release 后、第一次专家调用前执行；只读脱敏包。输出 `reports/expert-plan.v1.json`，不修改已冻结的 bundle。六基础角色是最低覆盖，不是领域穷尽承诺。

## 规划阶段

1. 交易画像：识别我方立场、交易结构、法域和时间、行业、资金/交付/数据流、正文附件关系。未知事实进入 open_issues；可以继续已知部分审核，不能以“中立”“其他”掩盖缺口。
2. 角度矩阵：以 deep-audit 的18领域为基线逐项判定，按实际交易展开子领域。每个适用角度分配主审 owners 和独立质询 challengers，二者不能相同。新的事实、规范层级或技术问题触发追加角度。
3. 组队：保留 legal/dispute/finance/business/compliance/language；必要时追加稳定角色 ID，例如 security、construction、employment、foreign_law、healthcare。专项角色仍阅读全文；不得只收到命中关键词的片段。
4. 初始化：每角色明确触发理由、待判断问题、专项知识边界、全文/上下文策略、工具及权限、结果规范、升级条件。设定并不赋予执业资格，也不证明能力。
5. 就绪：实际检查材料可读、上下文批次可分配、工具可用、任务有人负责。运行下方门禁，再调度 agent；有缺口仍可开展不依赖该缺口的工作，但交付状态保持部分审核。

默认所有角色先独立阅读，R1 不共享他人发现；R2 联结原文及证据，R3 交换质询，R4 对修改和分歧回归。长文本逐段账本与原文取回见 experts.md。不要用全局摘要替代片段审核，也不要索取隐藏思维链；输出可核验的证据、推断摘要和反例。

## 工具规划

每个工具记录真实 availability；尚未接通不填写可用。web search 用抽象问题找官方法源，网页/PDF读取用于核对原文、版本和适用条件。普通读取不足时才用浏览器/CDP操作动态页面，合同内链接不自动执行。金额/日期关系用确定性计算。版面/OCR在本地提取阶段处理，不向云专家开放原件。

`data_scope`仅支持 public_abstract_query（外部检索不得带合同内容/身份）、released_bundle（仅已发布脱敏包）、local_no_model（本地工具操作但内容不得送入模型）。工具列表是权限约定，不是技术隔离；宿主不能提供白名单时报告指令隔离局限。不得把“无训练”当作零留存、不得把匿名化当作客户同意第三方处理。所有外部发送仍服从用户授权。

## 阵容复评与版本

R1后、R2发现新关系后、R3出现跨领域分歧时复评。增派必须说明未覆盖问题及触发原文；不能仅为增加人数。生成新文件 `expert-plan.v2.json`，递增 revision，保留 change_log 和旧文件；用 `--activate` 登记新计划后才能分发。即使新计划 blocked 也须登记，旧 ready 计划不能继续冒充当前结果。新角色先完成独立全文基线，再补齐全部四轮；已有角色对新增关系、法源和修改重新检查，并对最新计划重新确认结果。旧结论不能只改摘要冒充复审。

每个专家结果及 audit-depth 均携带最新 `plan_digest`（对完整计划 JSON 使用 pipeline.digest）。结果校验依据该计划中的全部角色，而非固定六角色。删除角色不得用于绕过失败；六基础角色不能删除，专项撤销须有不适用证据、保留历史及相关结论。

补审最多两轮；受并发/预算/工具限制无法完成时记录 open_issues，不无限增派、不清空缺口。运行失败按专家失败重试上限处理。

## 数据契约

`schema_version:1, input_digest, revision:正整数, profile, experts:[], coverage:[], open_issues:[], change_log:[]`。

- profile：transaction、party_position、jurisdictions、industry、data_flow、documents 六个非空脱敏描述；不确定性进入 open_issues，深度协议另校验范围确认状态。
- experts：`{role,trigger,mandate,escalation,context_strategy,full_text:true,independent_first:true,readiness:"ready|blocked",tools:[]}`。role 为小写英文、数字或下划线，首字母英文，最长64字符。
- tools：`{name,purpose,required:true|false,available:true|false,data_scope:"public_abstract_query|released_bundle|local_no_model"}`。
- coverage：`{angle,status:"applicable|not_applicable|unknown",reason,owners:[],challengers:[]}`；angle 包含全部18领域，可增补；适用项主审和质询角色必须存在且不重合。
- open_issues/change_log：非空字符串组成的数组，可空；open_issues 只保存真正未决问题，不把已识别风险当作未审。

运行 `python3 scripts/expert_plan.py --run <run> --plan <plan> --activate` 初始化或推进当前计划。该显式操作原子写入 private/active-plan.json，记录输入摘要、revision和plan_digest；相同版本相同摘要可重复，更新必须严格增加revision，不能回退。主agent独占计划写入；这不是抵抗拥有本地写权限人员篡改的安全边界。

省略 `--activate` 只检查候选计划，不改变当前计划。validate/report/validate_depth要求所传计划与当前登记完全相同，未登记不能通过。新计划未就绪时仍登记后返回部分审核；不要因返回2回滚旧计划。返回0仅证明声明的规划结构就绪；不证明真实权限、专业理解、实际执行或法律全面性。所有 validate/report/validate_depth 调用传同一个 `--plan <plan>`。缺少计划的旧结果仍可校验基础结构，但深度状态会返回 `PARTIAL_AUDIT / EXPERT_PLAN_NOT_VALIDATED`。

新增交付给人类专家：角度责任矩阵、专家角色及触发理由、工具不可用项、阵容变更记录、未决范围；执行计划与真实完成记录分开展示。

计划coverage与audit-depth.legal_domains须逐ID和适用状态完全一致，包括所有新增领域；变更判断须修订并激活计划，不能在深度报告悄悄改为不适用。每个适用领域仍须关联核验法源。
