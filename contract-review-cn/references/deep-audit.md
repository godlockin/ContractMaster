# 全文、多轮与法源覆盖协议

本协议是默认审核要求。覆盖目标是**本合同事实下适用的规范**，不是宣称世界上所有法律都被检查。固定清单只能作为入口；必须允许新行业、新地区、新交易要素触发扩展。未提供地区、时间或交易事实时，保留范围缺口，不能把未知填写为不适用。

## 1. 每个字进入处理范围

原文保留字、数字、标点、空格、换行；不删除短句、脚注、表格、附件或看似无关文字。每文档的 segments 必须从0起无间隙无重叠地覆盖到最后一个字符，并能精确拼回全文。映射记录被隐藏值的每次出现位置；隐藏内容以标记进入语义审核，真实姓名等不会因此被云专家验证，须明确该限制。

PDF页、DOCX表格、页眉页脚、签署栏、手写和图片是原件覆盖清单的一部分。字符账本只能证明**提取文本**的覆盖；原件漏提、OCR错字、视觉关系仍需本地核对。不能以文本覆盖100%替代原件完整性证明。版本更新重新建立摘要与覆盖账本。

## 2. 法律适用范围及查漏

建 `scope`：法域、相关地区、签署/履行/争议日期、双方角色、行业、交易类型；每项提供值及 confirmed/assumed/unknown。推定中国大陆可继续审，但 unresolved事实或时间适用问题必须保留。

每个 `legal_domains` 项逐一作 applicable/not_applicable/unknown 判断，写合同触发事实或排除理由。适用项须挂经核验法源，不适用不能只写“无关”。基线：

| ID | 领域 |
|---|---|
| civil_contract | 民商事、意思表示、效力、权利义务与救济 |
| entity_authority | 主体、公司治理、签署权限、代理与担保 |
| procedure_evidence | 诉讼/仲裁、管辖、时效、通知及证据 |
| tax_accounting | 税务、会计、发票、支付结算 |
| labor_social | 劳动、劳务、社保及用工安排 |
| consumer_product | 消费者权益、产品质量、质量责任 |
| competition_integrity | 竞争、反垄断、商业贿赂及诚信 |
| licensing_industry | 行政许可、资质、行业专项监管 |
| finance_payments | 金融、融资、保险、支付及相关监管 |
| ip_trade_secret | 知识产权、许可、成果归属及商业秘密 |
| personal_information | 个人信息、敏感信息、处理角色与权利 |
| data_cybersecurity | 数据及网络安全、数据分类与风险管理 |
| cross_border | 涉外适用法、数据/货物/技术跨境及出口管制 |
| real_estate_construction | 土地、房屋、建设工程及相关许可 |
| environment_safety | 环境保护、安全生产及职业健康 |
| public_procurement | 招投标、政府采购、国资及公共资金 |
| local_special | 地方性规定、地域及特殊区域要求 |
| standards_contractual | 强制/推荐/行业/合同纳入的标准及企业政策 |

允许追加 domain。行业专项继续展开，如医药、教育、电信、能源、互联网服务；不能仅凭一级领域已勾选就声称其下规范查完。

同时按 `source_searches` 覆盖规范层级：law、administrative_regulation、local_regulation、department_rule、local_rule、judicial_interpretation、normative_document、standard、treaty_foreign。每类记录检索式、入口、日期、结果或不适用理由。案例、企业政策、合同惯例可另加类别，不能混成强制法律义务。

法源查漏顺序：由合同事实检索 → 阅读相关规范及配套引用 → 沿授权/定义/例外/实施细则继续检索 → 查看修订/废止/过渡安排 → 独立角色反向检查遗漏的规范类别。法律/法规/规章/政策/标准的效力与适用关系须分别解释；违反某项规范不自动等于整个合同无效。

每个 `sources` 记录标题、制定机关、具体来源链接、类型、版本、施行及失效日（仍有效可null）、核验日、条号、适用事实。verified为专家核验声明；程序只验证格式和关联，无法证明法源真实或穷尽。

公开检索入口（2026-09-07检查）：[国家法律法规数据库](https://flk.npc.gov.cn/search)含不同类别及有效性筛选；规章和规范性文件按主管部门及相关地方政府官方发布入口补查；[国家标准全文公开](https://openstd.samr.gov.cn/)及[全国标准信息公共服务平台](https://std.samr.gov.cn/)区分标准类别。入口页面本身不作为具体风险的法条依据。

## 3. 信息安全专项不能被合规总项代替

compliance角色负责以下全部项，business/法律角色交叉复核；复杂技术合同额外召唤信息安全专项agent，使用相同脱敏边界，不冒称已做系统渗透或认证。baseline `security_checks`：

- data_scope：数据类别、处理目的、权限及最小化。
- access_control：身份认证、最小权限、特权账号和离职回收。
- encryption_keys：传输/存储加密、密钥责任及可验证要求。
- logging_audit：日志范围、留存、审计权及取证可用性。
- vulnerability_change：漏洞分级、修复期限、补丁和变更责任。
- incident_response：事件分级、通报对象/时限、合作及损失承担。
- backup_recovery：备份、恢复测试、RPO/RTO及业务连续性。
- subcontractors：分包、第三方/云服务责任、审批和等效义务。
- retention_deletion：留存期限、终止返还、删除证明及备份副本。
- transfer_location：处理/存储地点、远程访问及跨境条件。
- verification_liability：安全验收、整改、检查权、保险与责任上限。

每项适用则提交reason、证据片段和outcome（satisfied/missing/unknown）；不适用须解释并将outcome写为not_applicable。未知结论阻断完整状态；已确定的缺失属于已发现风险，可正常交付。法律强制要求、合同约定和建议最佳实践分开，不假定所有交易都必须同一加密算法、认证、等级保护级别或通报期限。

## 4. 至少四轮，独立阅读后再交换意见

| 轮次 | 必须完成的任务 | 留存 |
|---|---|---|
| R1 local | 计划中全部角色独立全文逐字词句段审查；不看他人答案 | 每角色全部segment ID及其原始结果 |
| R2 relational | 重读定义、指代、例外、时间、金额、正文附件关系；建立有向关系和多跳链 | 每关系的两端片段、类型、结论；推理链的证据与结论摘要 |
| R3 adversarial | 交换结论；从对方立场寻找规避方式、反例、错误法源及失效条件 | 每角色对全部关系的复核记录，异议和处理结论 |
| R4 regression | 核实法源、复查未审文字及提出的修改对全文的影响；逐角色全覆盖复核 | 复核记录、修改影响和未决清单 |

先完成 [动态专家规划](expert-planning.md)。每轮均要最新计划中全部角色各一条轮次汇总，覆盖全部segment；R2—R4覆盖全部已发现relations，`review_note`只写可核验的审查结果摘要。角色复用按任务继续调用；后续轮允许交换脱敏意见，不能把第一轮复制四次。

关系类别不限于 definition、reference、exception、priority、timing、amount、obligation_remedy、data_flow。每片段没有关系也记录检查结论；所有新增关系须回到受影响角色复核。

多跳示例：**定义中的“交付” → 默示验收条件 → 尾款支付 → 异议权丧失 → 责任上限**。分别定位每一步原文，判断连接是否成立，检查反例和例外；输出证据链与简洁理由，不要求暴露模型内部思维过程。

`chains`至少覆盖发现的全部两跳关系组合（A→B→C且A≠C）；必要时继续到更多跳，不以两跳为停止点。`chain_frontier`留存尚未检查的延伸、缺失引用目标或上下文窗口限制；任何待处理项都阻止完整状态。循环引用要记录循环及解释，不能无限递归。程序检查关系覆盖和有依据的链结构，不证明语义推断本身正确。

程序按邻接关系枚举两跳组合，超过50,000组合时返回部分审核及分区复核提示，不会静默截断后判为完整。分区复核须包含跨区边和合并验证，未完成前保持未决状态。

补审最多两轮；到上限仍有新发现、未解冲突、缺失法源或事实则交付部分报告，列明缺口。不得为了结束而清空未决项。旧R1结果只作历史记录；修改版本必须重新绑定input_digest。

## 5. 交付门禁

执行 `python3 scripts/validate_depth.py --run <run> --depth <run>/reports/audit-depth.json --plan <run>/reports/expert-plan.v1.json --results <全部计划角色JSON路径>`。

缺少计划、专家未就绪、必要工具不可用或计划存在未决项，均不能申报完整；新增角色必须补齐全部四轮，结果与深度文件都绑定最新 plan_digest。

返回0仅表示“申报的范围内，结构与覆盖门禁满足”；不代表所有法律和风险已穷尽。返回2为结构错误或审核缺口；状态/数量仅写日志。需部分报告时仍可生成，但标题明确“部分审核／待复核”。`pipeline.py report --depth <路径>`会把深度校验状态纳入初稿；没提供时明确深度审核未验收。

不允许把存在unknown/assumed适用事实、unverified法源、unavailable检索、未解关系、chain_frontier或open_issues的任务写成完整通过。高风险**已发现且解释清楚**不等于审核未完成；风险尚未消除可以报告，不能因此抹掉风险。

## audit-depth.json 字段

`schema_version:1, input_digest, plan_digest, scope, scope_uncertainties:[], source_searches:[], legal_domains:[], sources:[], security_checks:[], relations:[], chains:[], rounds:[], chain_frontier:[], open_issues:[]`。

- scope：jurisdiction/locations/dates/party_roles/industry/transaction，每项 `{status:"confirmed|assumed|unknown", value:"脱敏事实"}`。
- source_searches：`{kind,status:"searched|not_applicable|unavailable",query,urls:[],checked_at:"YYYY-MM-DD",reason}`；not_applicable可空query/urls，其余须填写。
- legal_domains：`{id,status:"applicable|not_applicable|unknown",reason,source_ids:[]}`；适用必须关联至少一条法源。
- sources：`{id,title,issuer,kind,url,version,effective_from,effective_to:null,checked_at,articles:[],applicability,status:"verified|unverified"}`，日期YYYY-MM-DD；检索日不能早于发布于未来的事实判断，时间适用另行解释。
- security_checks：`{id,status:"reviewed|not_applicable|unknown",outcome:"satisfied|missing|unknown|not_applicable",reason,segment_ids:[]}`；reviewed须有片段，任一unknown阻断完整。
- relations：`{id,from:"segment ID",to:"segment ID",type,status:"resolved|unresolved",summary}`。
- chains：`{id,edge_ids:["关系ID","关系ID",...],status:"resolved|unresolved",summary}`；连续边必须首尾衔接，至少两条边，不重复边。
- rounds：`{round:1..4,role,segment_ids:[],relation_ids:[],review_note}`；每轮每角色一个汇总，全部片段和对应关系不得重复或遗漏。
- scope_uncertainties/chain_frontier/open_issues：待处理事项字符串数组，必须真实记录，不可用任意布尔值替代。

所有字段只含脱敏内容；身份与秘密值不进入法源检索、轮次摘要或证据链。新增交付：法律适用矩阵、法源目录、信息安全清单、跨条款关系/证据链、多轮覆盖与未决事项。

## 实际结果与计划一致性

所有领域ID及applicable/not_applicable/unknown状态必须与当前激活的计划一致，新增领域不能遗漏；差异须先修订并激活新计划。命令读取实际专家结果，任一finding含unverified依据或未解决questions都阻止完整；不得用空的depth.open_issues掩盖。历史问题可保留，使用result-contract的question_resolutions提供证据与解决理由；未核验依据必须核验后更新basis，不能靠问题已解决覆盖。未传入实际结果的底层深度评估保持EXPERT_RESULTS_NOT_LINKED。
