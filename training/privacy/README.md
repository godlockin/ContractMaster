# 契衡本地敏感信息模型实验

状态：研发实验，未自动接入真实合同审核。仅处理本仓库生成的虚构合同片段及许可已记录的公开合成样本。训练效果以每次实验的metrics.json为准，不以训练loss或测试数量宣称合格。

2026-09-14已完成四轮微调，按开发集选出第四轮160步检查点；开发集通过，三组保留测试未通过，禁止据此宣称合格。详见[实验报告](../../docs/PRIVACY-MODEL-EXPERIMENT-2026-09-14.md)。本次训练合计32.1分钟，不包含安装、下载、数据准备和评测时间。

随后增加本地容错解析、项目/地址/金额边界校正和离线重处理：原创保留集、挑战集达到分类门槛，公开中文对照仍明显不足。第七轮使用4186条公开样式虚构数据微调80步，但开发集精确率降至84.36%，未采用。最终候选通过两套独立虚构盲测（80条、100条），但公开中文对照仍未通过，不能宣称整体合格。

## 数据和工件

- 第一轮原创训练640条，第二轮扩至1600条；开发64条、保留测试100条。措辞家族分开、实体库存分开，未由独立专业人员标注。
- 第三轮训练2827条：原创1600、公开训练186条重复4次、地址额外重复483条；重复不算独立样本。
- 第四轮训练2386条：原创1600、开发错误驱动的新训练600、公开训练186。回到第二轮权重，使用新优化器继续微调。
- 外部评测：固定版本OpenPII中文验证集92条，保留供应方精确字符坐标；不进入训练。另有20条手写虚构挑战集。
- 模型：Qwen3-1.7B的MLX 4bit转换，固定revision；上游大文件SHA256、尺寸和本地文件摘要均核对。
- 模型、数据、适配器、原始预测放在Git忽略的`artifacts/privacy/`；不得将未来真实合同训练所得权重默认公开。

准备工具均不读取用户合同。`fetch_model.py`仅下载固定模型，`fetch_public.py`通过显式split分开下载公开训练和验证来源。联网准备完成后，train/evaluate按本地路径加载，禁用远程代码及训练遥测；这些设置不构成操作系统网络隔离保证。

OpenPII来源为Ai4Privacy / Ai Suisse SA的[公开数据集](https://huggingface.co/datasets/ai4privacy/pii-masking-openpii-1.5m)，固定版本`a785eb528e28be2693c3718a27e066970de5dadb`，数据卡声明[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。本项目进行了中文筛选、类别映射及格式转换，供应方标注未经独立人工复核。模型版本与完整性以`verified-download.json`为准。

## 重现

在项目根目录执行，按宿主后台日志规范封装。首次创建独立环境后安装`requirements-lock.txt`，不要替换项目原有审核虚拟环境。锁定依赖对应本次macOS、Python 3.14环境，不代表跨平台兼容。

```bash
python3 -m venv .venv-privacy
.venv-privacy/bin/python -m pip install -r training/privacy/requirements-lock.txt
python3 training/privacy/fetch_model.py --output artifacts/privacy/models/qwen3-1.7b-4bit
python3 training/privacy/prepare_data.py --output artifacts/privacy/data/v2
python3 training/privacy/prepare_data.py --output artifacts/privacy/data/v3 --count 1600 --recipe expanded-v2
python3 training/privacy/fetch_public.py --output artifacts/privacy/data/openpii-zh-v4
python3 training/privacy/fetch_public.py --split train --limit 200 --output artifacts/privacy/data/openpii-train
python3 training/privacy/prepare_challenge.py --output artifacts/privacy/data/challenge-v1
.venv-privacy/bin/python training/privacy/evaluate.py --mode hybrid \
  --data artifacts/privacy/data/v2/dev.jsonl --output artifacts/privacy/evals/base-dev
.venv-privacy/bin/python training/privacy/train.py --config training/privacy/configs/qlora-v1.json
.venv-privacy/bin/python training/privacy/evaluate.py --mode hybrid \
  --adapter artifacts/privacy/adapters/v1 \
  --data artifacts/privacy/data/v2/dev.jsonl --output artifacts/privacy/evals/v1-dev
.venv-privacy/bin/python training/privacy/train.py --config training/privacy/configs/qlora-v2.json
python3 training/privacy/prepare_mixed.py --output artifacts/privacy/data/v5
.venv-privacy/bin/python training/privacy/train.py --config training/privacy/configs/qlora-v3.json
python3 training/privacy/prepare_augmentation.py --output artifacts/privacy/data/v6
.venv-privacy/bin/python training/privacy/train.py --config training/privacy/configs/qlora-v4.json
python3 -m unittest discover -s training/privacy -p 'test_*.py'
```

输出目录拒绝覆盖。失败目录保留用于诊断，重试选择新的实验编号；原始下载允许续传并验证。不要把保留测试集复制到MLX训练目录。

候选评测分别使用开发集、100条保留集、92条公开中文对照、20条挑战集，输出名称为`候选编号-dev/test/public/challenge`。`report.py`校验完整样本数量、数据摘要和适配器身份；缺失、部分评测、任一失败都不能通过整体验收。

本次候选`v4-step160`通过复制第四轮的`0000160_adapters.safetensors`、`adapter_config.json`和`provenance.json`建立独立目录，保留`selection.json`选择依据。`coverage_audit.py --evaluation <评测目录>`从已保存预测补充不计实体类型的遮盖覆盖率，不重跑推理、不改变分类验收门槛。

## 本地脱敏入口

能力探测（只检查模型文件、版本和本地依赖，不读取合同）：

```bash
python3 training/privacy/model_status.py
```

`redact_local.py`只读取本地UTF-8文本，在本机加载基础模型和适配器，输出`redacted.txt`与权限为600的`mapping.json`。模型输出必须能在原文定位；解析失败、输入超长或实体无法验证时直接阻断，不返回“无敏感信息”。`--backend auto` 优先本地模型，模型缺失/依赖缺失/完整性异常时安全降级为规则和案例词典；`--backend local` 强制模型且不可用即失败；`--backend rules` 仅规则演练。三种模式都不上传原文。

```bash
.venv-privacy/bin/python training/privacy/redact_local.py \
  --input /path/to/local.txt \
  --output /path/to/new-local-result
```

案例首次使用先创建并编辑本地策略（不要把真实值粘贴给大模型）：

```bash
python3 contract-review-cn/scripts/privacy_config.py init --root /path/to/case
python3 contract-review-cn/scripts/privacy_config.py check --config /path/to/case/privacy-policy.json
```

策略需覆盖主体、人名/别名、联系方式、地址、证件/账户、项目代号、内部价格和技术秘密，并明确合同金额、期限、比例能否进入公开包。公开包必须经过人工提取及隐私复核后才能交给大模型。

入口不提供远程回退或自动上传；环境变量仅关闭模型库联网和遥测，不等于操作系统级断网。真实合同使用前应在本机自行启用网络隔离、磁盘加密、备份控制和最小权限，并先人工检查替换结果。

## 固定评测口径

以原文字符位置及类别计算precision/recall，合并同类重叠区间避免重复计数；另报整段无遗漏率、完全匹配率、格式有效率和按类型计数。公开样本仅在其标注可覆盖的类型范围评分，不把缺少ORG标注视为模型误报，但也不证明ORG识别能力。

试验目标：字符召回≥99%、精确率≥95%、无无效输出。PASS_CONTROLLED_BENCHMARK仅表示所测数据集达到数值目标，不证明真实合同合格或零泄露。任何测试集不达标须单独列出，不能平均到其他测试集里消除失败。

模型输出必须是JSON数组，实体逐字存在于原文；虚构实体、未知类别或截断都计失败。模型不可以撤销规则命中。规则基线使用生产脱敏器相同的最长优先消重，避免把身份证内账号误匹配重复计为不同类别。

选择与迭代只依据开发集。保留集仅用于选定候选的评测；一旦使用某保留集错误驱动后续训练，它转为开发资料，下一轮须建立新的独立保留集。

## 已知边界

中文合成合同数量有限；统一社会信用代码等类别尚需足量独立样本。公开数据的姓名/地址粒度、标签定义和标注质量与合同策略存在差异。特别是“哪些业务数据属于秘密”需要明确策略，模型无法自动代替企业决定。

当前模型评测对象是文本短片段；未完成整份合同、跨页表格、扫描件OCR、图片印章或组合信息重识别的模型验收。开发集64条来自8类模板，不能把这些模板上的高分解释为全面泛化。超过输入限制会记为失败，不静默截断。

本阶段不修改既有发布门禁，不自动导出模型发现的内容，不调用远端法律模型。资格报告通过之前不推荐使用用户合同；后续用户合同验证必须采用本地受控流程。
