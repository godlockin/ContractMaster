# AI IDE 中的案例目录管理

本项目是 skill。由加载它的 AI IDE 执行随包 Python 脚本，管理用户工作区文件；无需独立应用、数据库或常驻服务。

## 目录选择与自然语言入口

- “在当前目录管理合同”：默认 `<当前工作目录>/contract-cases/`。
- “在 ~/合同审核 下建立案例库”：使用用户指定的新目录作为 `--root`，后续每次显式传同一根路径。
- “把这份合同加入 C001”“对方返回新版，比较 S1 和 S2”：先运行 list 定位案例、稳定合同编号及基准快照，再导入和准备。
- 新真实审核默认进入案例树。已有单次 run 可继续原流程，不自动迁移或覆盖。仅讨论技能开发或用法时不创建真实案例。

主 agent 使用 AI IDE 提供的用户工作目录，不能把技能安装目录当作业务目录；若用户工作区就是技能源码仓库，实际材料使用用户指定的外部目录。根目录已有 store.json 时直接 list；init 不接管已有普通目录，改用其下新的 contract-cases 子目录并告知路径。根路径使用绝对路径；CLI 默认只是执行时 cwd，启动脚本前不要切换到技能目录。符号链接路径不支持，使用真实物理目录。

只在输入版本、合同身份或比较基准有歧义时追问。可以自动分配 C001、D001、V1、S1、R1 等不含真实客户名的标识；版本顺序按明确前序记录，不按文件名或接收时间猜测批准状态。分支 V2/V3 均可指向 V1，比较时明确选择两份快照。

## 目录树与索引

```text
contract-cases/
  .gitignore                     # 忽略案例库全部业务数据
  store.json                     # 格式标识
  private/cases/C001/
    case.json                    # 案例标识、创建时间、可选私有背景
    contracts/D001/versions/V1/
      original.docx              # 导入副本，固定名称，保留原始字节
      version.json               # 前序版本、原始文件名、时间、摘要
    snapshots/S1.json            # 合同组完整清单：D001=V1、D002=V3…
    reviews/R1/
      binding.json               # 案例、两份快照、输入及比较摘要
      run/
        private/                 # 提取原文、映射、未复核候选包
        public/bundle.json       # 仅 release 后存在
        reports/versions/v000001/ # 报告、结果及manifest
```

一个案例可包含多份合同、附件；D001 等是稳定文件身份，不是版本号。`--group` 可区分案例内合同组，默认 main；同一比较两份快照必须属于同组。每个快照须显式列出该轮全部成员，不自动继承 parent 成员。未列入的新旧差集就是整份增加/删除，必须结合用户材料清单核实，不能把漏导入解释成对方有意删除。

各层 JSON 是持久索引的唯一来源；`list` 本地汇总并验证原件、快照、审核绑定及编号报告的摘要，不另维护容易过期的数据库。返回编号、父版本、组成员、审核路径、已发布包存在状态和报告索引；不返回真实文件名、背景或正文。可用 `list --case C001` 限定范围。发现改写即失败，不跳过损坏数据返回虚假的完整列表。报告深度只是已存声明，索引完整性检查不代替审核验证或法律签核。

## AI IDE 操作示例

以下命令由 agent 按宿主后台执行规范调用；用户无需执行命令或填写 JSON。`SKILL_DIR` 指技能目录，`CASE_ROOT` 指用户业务目录，两者分开。路径参数按数据引用，不能执行路径中的 shell 表达式。

```bash
python3 "$SKILL_DIR/scripts/case_store.py" --root "$CASE_ROOT" init
python3 "$SKILL_DIR/scripts/case_store.py" --root "$CASE_ROOT" create --case C001
python3 "$SKILL_DIR/scripts/case_store.py" --root "$CASE_ROOT" import \
  --case C001 --contract D001 --version V1 --input /本地/我方初稿.docx
python3 "$SKILL_DIR/scripts/case_store.py" --root "$CASE_ROOT" snapshot \
  --case C001 --snapshot S1 --member D001=V1
python3 "$SKILL_DIR/scripts/case_store.py" --root "$CASE_ROOT" import \
  --case C001 --contract D001 --version V2 --parent V1 --input /本地/对方返回.docx
python3 "$SKILL_DIR/scripts/case_store.py" --root "$CASE_ROOT" snapshot \
  --case C001 --snapshot S2 --parent S1 --member D001=V2
python3 "$SKILL_DIR/scripts/case_store.py" --root "$CASE_ROOT" prepare \
  --case C001 --snapshot S2 --baseline S1 --review R1
python3 "$SKILL_DIR/scripts/case_store.py" --root "$CASE_ROOT" list --case C001
```

附件用独立 D 编号 import，snapshot 重复 `--member` 列入；单版本全文审核省略 `--baseline`。prepare 可传 `--entities /本地/实体词典.json`。create 可传 `--metadata /本地/案例背景.json`，内容仅本地保存，不能为获得背景而读取私有文件到模型；使用用户主动提供或已复核脱敏的背景。

案例 prepare 按 D 编号建立显式对应关系，支持中间附件缺失和参数重排，不受独立 prepare-change 按参数顺序配对的限制。任意两份同组快照可比较，不局限相邻版本。

prepare 返回确切 `run` 路径。后续按 [workflow](workflow.md) 对该路径执行提取/隐私复核、release、专家计划、双组审核、validate 和 report；`--revision` 保存报告修订，不能替代合同 V 或快照 S。专家输出和计划放该 run 内，报告完成后再次 list 提供对应链接。只将已确认发布的 bundle 和脱敏背景交给审核 agent，绝不把整棵案例目录作为专家上下文。

## 完整性与边界

- 导入复制原件，不移动用户文件；既有版本、快照、审核编号拒绝覆盖。后续版本显式声明 parent，原件内容摘要与快照/审核绑定持续校验。
- 写入使用锁、临时目录/文件及原子发布。准备失败清理临时产物，可原编号重试。遗留 `.write-lock` 时先确认没有写入进程，再人工处理锁；脚本不擅自抢锁。崩溃遗留 `.pending-*` 不计入索引，不自动认定成功。
- 目录权限及 .gitignore 是本地保护，不是 IDE 文件沙箱；案例库禁止提交 Git。自动只输出索引摘要；private 中的 case.json、原件、候选包和映射仍禁止进入模型。已发布包虽位于案例树 private 祖先下，仍按其内容发布状态判断可分发性。
- 本轮支持文件身份、版本分支、组快照、任意基准比较与报告索引。尚无自动跨轮风险合并、人工批准/签署状态机、多用户权限或旧 run 迁移命令；不能从“最新版本”推导“可签”。
