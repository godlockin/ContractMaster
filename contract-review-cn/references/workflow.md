# 可执行 workflow

## 状态及产物

`NEW → PREPARED_PRIVATE → EXTRACTION_AND_PRIVACY_REVIEWED → RELEASED → EXPERT_PLAN_READY → EXPERTS_RUNNING → RESULTS_VALIDATED → ADJUDICATED → DELIVERED`

新任务默认双组计划v2，详见[双组协议](dual-team.md)。所有results参数必须包括A/B两组，下面基础六角色路径仅示意，另加入reverse_legal、reverse_compliance、reverse_dispute及专项结果。

EXPERT_PLAN_READY按[动态专家规划](expert-planning.md)执行：交易画像、角度矩阵、六基础及专项组队、上下文和工具配置、就绪校验。计划版本绑定所有专家结果及深度报告。

EXPERTS_RUNNING内部强制R1独立逐段→R2跨条款多跳→R3反证质询→R4回归。详细适用矩阵、信息安全、证据链和深度门禁见[deep-audit.md](deep-audit.md)。只有基础validate和validate_depth都通过才允许申报完整；缺口存在可交付部分报告，不能伪造完整。

prepare/release/expert_plan/validate/report 是脚本门禁；EXPERTS_RUNNING、ADJUDICATED、DELIVERED 由主 agent 在脱敏报告中记录真实状态。脚本不自动调用模型，也不自动认定法律有效性。

运行目录：

```text
run/
  private/                 # 绝不能分发
    source-0001.txt         # 提取原文
    extraction.json        # 原件本地路径、摘要、质量提醒
    mapping.json           # 稳定标记、真实值、双坐标
    candidate.json         # 尚未获准分发
  public/bundle.json       # 仅 release 后出现
  reports/                 # 专家 JSON、脱敏报告
  audit.jsonl              # 仅阶段、时间、数量/摘要；无内容
```

## 本地命令

先执行 `python3 "$SKILL_DIR/scripts/pipeline.py" doctor --input /本地/合同.pdf` 探测格式与依赖，不安装软件、不读取正文。按[input-formats](input-formats.md)提供可选安装/转换引导。prepare可以保留成功文件，未处理文件写入冻结包的input_gaps并阻止深度完整状态；全部失败则不生成候选包。补齐输入后使用新运行目录重新处理，旧结果不可复用。

参数应由宿主作为结构化 argv 传递或正确 shell 引号保护，不拼接不可信合同文本。以下命令放入用户已有后台 wrapper 执行；只返回退出状态和短错误码，读取 private 的内容操作不能回传模型。

```bash
python3 "$SKILL_DIR/scripts/pipeline.py" prepare \
  --input /本地/合同.docx --input /本地/附件.txt \
  --entities /本地/实体词典.json --run /本地私有目录/全新运行编号

# 用户在本地核对提取与脱敏后；两个 attest 对应用户真实确认
python3 "$SKILL_DIR/scripts/pipeline.py" release --run /本地私有目录/运行编号 \
  --attest-extraction-reviewed --attest-privacy-reviewed

# release 后生成脱敏 expert-plan.v1.json，验证就绪后调度真实专家
python3 "$SKILL_DIR/scripts/expert_plan.py" --run /本地私有目录/运行编号 \
  --plan /本地私有目录/运行编号/reports/expert-plan.v1.json --activate

# 主 agent 调度全部计划角色写 JSON，随后（示例仅列基础角色，专项结果也须加入）：
python3 "$SKILL_DIR/scripts/pipeline.py" validate --run /本地私有目录/运行编号 \
  --plan /本地私有目录/运行编号/reports/expert-plan.v1.json \
  --results /本地私有目录/运行编号/reports/legal.json \
  /本地私有目录/运行编号/reports/dispute.json \
  /本地私有目录/运行编号/reports/finance.json \
  /本地私有目录/运行编号/reports/business.json \
  /本地私有目录/运行编号/reports/compliance.json \
  /本地私有目录/运行编号/reports/language.json

python3 "$SKILL_DIR/scripts/pipeline.py" report --run /本地私有目录/运行编号 \
  --revision 1 \
  --plan /本地私有目录/运行编号/reports/expert-plan.v1.json \
  --depth /本地私有目录/运行编号/reports/audit-depth.json \
  --results /本地私有目录/运行编号/reports/{legal,dispute,finance,business,compliance,language}.json

# 仅在用户要求恢复身份时：
python3 "$SKILL_DIR/scripts/pipeline.py" restore --run /本地私有目录/运行编号 \
  --input /本地私有目录/运行编号/reports/versions/v000001/report.md \
  --output /本地私有目录/运行编号/private/restored-report.md
```

prepare 失败不继续；修正输入后用新运行目录。release 拒绝缺少确认、已发布、空文档、候选包摘要不一致。validate 非零时不允许 report 成功；补审对应角色后重试，不重复提取无变更输入。

补审使用新的正整数revision，成功版本不可覆盖；报告、结果快照、摘要清单整体提交到reports/versions/vNNNNNN。清单记录输入、计划、深度、结果与报告摘要，签核状态保持NOT_ATTESTED。保留原版本计划与深度文件。审计准备失败时版本尚未提交，修复后可重试同编号；旧调用未传revision仍写reports/report.md。

release 还核对原件、实体词典及映射摘要。发布后报告绑定冻结的 `input_digest` 快照，不代表随后修改的原件；新版本必须创建新运行。验证脚本本地检查结果中是否含已知敏感值，不能替代对未知泄漏的复核。

## 提取质量

- TXT/MD：保留所有 Unicode 字符及换行，不清洗、不纠错、不 normalize。每段带精确坐标；原始文件字节 SHA-256 仅存 private。
- DOCX：按 XML 顺序提取段落和表格文本，页眉页脚、脚注、尾注、批注分文档；探测图片、文本框、修订、域、嵌入对象后发出质量提醒。扁平化不能保证视觉关系，必须本地对照。复杂编号/合并单元格/多栏/签章可能丢失语义；需要本地转换、OCR、人工转录后将核验后的 TXT 作为补充输入，避免云 OCR。
- PDF：pypdf 仅文本层，每页独立文档；空白提取页直接失败（用户可核实真正空白页后本地转 TXT）。图像及异常字符提醒人工核对。OCR 采用用户选定可信本地引擎；脚本不附带 OCR 模型。保留页码与提取证据，无法读取的页标为未审。
- `.doc`、图片、加密文件、扫描 PDF 不假装支持；提示本地转换后新运行。所有附件均显式 `--input`，合同中提及但缺少附件计入风险。

## 字词句到上下文

片段保存完整字符流，标点和换行也在覆盖范围；不得按摘要替代逐段审核。五层检查由每专家逐段记录：
1. 字：错别字、OCR 混淆、漏字、多字、数字/符号/标点、手工填空。
2. 词：定义、否定、范围、义务强度、数量词与歧义。
3. 句：主体/行为/条件/例外/期限/后果是否闭合。
4. 段：权利义务、机制完整性、缺项、不公平分配。
5. 上下文：全文定义一致性、引用、附件顺序、例外冲突、执行链及救济。

逐字不要求每个字生成一条风险；用完整文本 span 加逐段审阅记录避免高噪声输出。chunk 在约 3000 字切开长行，跨 chunk 的句段必须拼接检查，不能误认为原始段落边界。

## 法源核实

优先国家法律法规数据库 https://flk.npc.gov.cn/、全国人大 https://www.npc.gov.cn/、最高人民法院 https://www.court.gov.cn/、中国政府网 https://www.gov.cn/ 及主管部门官方站点。运行时检索，不把研究时点当作永远有效。记录发布日期、施行日、修订/废止情况、合同相关日期、地域/主体/行业条件；法规、司法解释、部门规范、案例和商业偏好分开标记。案例要案号、法院、裁判日、程序状态及可核实链接，不能虚构“法院一般会”。外网不可用时输出未核实项及相应结论限制。

## 交付

report 命令只生成按严重度排列的全部发现初稿，不自动去重或给“可签”结论。主 agent 补充：我方立场与假设、最高风险、逐项证据/后果/建议、法源核验、冲突裁决、缺失附件、脱敏导致的不可判断项、提取局限、失败/补审记录。重要合同最终签署决策需要具备授权及完整事实的负责人复核，不能将模型自检替代该判断。
