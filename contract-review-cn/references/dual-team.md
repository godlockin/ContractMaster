# 双组独立审核（计划 schema_version=2）

新任务默认采用本协议。A组从条款推导风险，B组从法律、法规、监管要求及争议场景反推遗漏、例外和可被利用之处。两组既查漏也减少误报，不设置必须发现漏洞的配额。

## 阵容和独立性

- A组：legal、dispute、finance、business、compliance、language，保留六背景。
- B组：reverse_legal（效力/强制规范/法源遗漏）、reverse_compliance（法规规章/许可/行业监管）、reverse_dispute（争议/举证/规避路径）；按合同增派逆向专项。
- experts增加team=A或B；role全计划唯一。适用coverage的owners来自A，challengers来自B。两组各读全文、每角色完成四轮。
- 每名专家不同宿主上下文，首次fork_turns=none。R1不读取任何其他专家答案，包括同组；协调者不提前给B组A组的发现、法源排除意见或摘要。
- 容量允许时同时调度两组；容量不足时混合分批，如legal/reverse_legal/finance，再compliance/reverse_compliance/business，再dispute/reverse_dispute/language。R1全部冻结后才交换意见；分批不称为九人同时运行。

## 四轮

| 轮次 | A组 | B组 | 交接条件 |
|---|---|---|---|
| R1 独立 | 条款、履行和风险基线 | 独立适用范围、规范查漏、争议场景 | 各自原始结果和声明冻结，不互看 |
| R2 关系 | 定义/例外/附件/救济关系 | 规范和反例检查遗漏与规避 | R1冻结后交换 |
| R3 质询 | 回应B，质疑B的误报和前提 | 质询A的遗漏及修改建议 | 每个适用领域双向质询，每项发现被对组复核 |
| R4 回归 | 核对修改与裁定 | 检查修订引入的新漏洞 | 保留未解分歧，不按多数票清除风险 |

每组独立检查全部领域与9类法源，分歧经R3解释后汇入最终适用矩阵。检索仅使用抽象法律问题，不发送合同正文。无发现也提交查漏依据。

## 数据字段

expert-plan沿用字段，schema_version=2，每个expert新增team。旧计划升级提高revision并激活，不能只改版本号伪造复审。

每角色结果增加team、first_pass：

```json
{"context_id":"宿主独立上下文ID","other_results_read":[],
 "input_digest":"当前输入摘要","plan_digest":"当前计划摘要",
 "segment_ids":["全部片段ID"],"summary":"独立首审结论摘要及限制"}
```

首审声明冻结后不得改写来掩盖已读其他答案。另存R1原始结果和宿主调用证据；first_pass不是实际执行证明，不包含隐藏思维链。

audit-depth沿用schema_version=1，计划v2另要求：

- team_passes：恰好A/B两项。`{team,first_pass_digests:{role:digest(first_pass)},domain_checks:[],source_checks:[]}`。
- domain_checks覆盖最终法律矩阵全部ID；source_checks覆盖9类法源。每行`{id,status:reviewed|not_applicable|unknown,reason}`。reason写本组检查依据及适用/排除理由；unknown阻断完整。URL及法源细节仍放source_searches/sources。
- R1的round记录新增first_pass_digest；全部角色仍完成每轮全文覆盖。
- cross_challenges每项：`{id,author,target,angle,question,response,status:resolved|unresolved,outcome:upheld|corrected|rejected|open,reason,evidence_refs:[],finding_ids:[]}`。
- author/target必须跨组；证据为非空有效segment/source ID；finding_ids只能引用目标组发现，领域级查漏可为空。
- 每个applicable领域至少A→B、B→A各一条，每项最终finding被对组质询。未解决用unresolved/open；其余裁定均须理由及证据。upheld保留原结论，corrected修正，rejected驳回。

摘要统一pipeline.digest。报告展示质询、回应、裁定、证据；保留被修正/驳回的原始档案及ID，不抹掉历史。

## 完成门禁

旧计划v1只能部分审核，带DUAL_TEAM_PLAN_REQUIRED。v2缺组、重复上下文、首审污染、片段遗漏、摘要陈旧、缺轮次/组清单会失败。缺双向领域质询、未复核发现或未解决挑战时保持PARTIAL_AUDIT。

这些是结构及独立性声明检查。不同context_id不能证明宿主隔离，摘要不能证明真实并行。真实执行需宿主原生记录；协议升级不等于已运行真实专家审核。
