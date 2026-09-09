# 开始使用

| 目标 | 需要什么 | 入口 |
|---|---|---|
| 不安装，先看效果 | GitHub/浏览器 | [完整样例](WALKTHROUGH.md) |
| 本地体验处理 | Git、Python 3.10+ | `python3 demo.py`，不调用模型 |
| 审自己的合同 | Codex宿主、skill、Python、文件工具与模型 | 提供文件路径和立场 |
| 评价结果 | 专业判断、浏览器/表格软件 | [人工复核包](../research/public-contracts/RUN-REPORT.md) |

## 安装与环境

macOS/Linux首次安装示例；当前本地测试环境为macOS，Windows和其他宿主尚未实测。目标已存在时先备份、核对版本，避免嵌套复制。

```bash
git clone --branch miao https://github.com/godlockin/ContractMaster.git
cd ContractMaster
mkdir -p "$HOME/.codex/skills"
cp -R contract-review-cn "$HOME/.codex/skills/contract-review-cn"
```

开启能发现该skill的新会话，或刷新宿主技能；非默认目录按宿主配置调整。Python需在agent命令环境中可用。TXT/MD和基础DOCX解析使用标准库，文字层PDF额外需要 `pypdf`：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade -r requirements-pdf.txt
```

告诉agent使用该虚拟环境解释器，终端激活不保证桌面宿主继承。仓库已有样例PDF，无需安装 `reportlab`；仅重新生成该PDF时需要此库及中文字体。

PDF 依赖固定为通过测试的 pypdf 6.18.0。更新版本时修改 requirements-pdf.txt，并按 README 使用 `.venv/bin/python` 跑全量验证；系统 `python3` 不会自动使用项目虚拟环境中的库。

## 提供材料

依赖按输入格式引导安装，不是启动时必装：DOCX、TXT、MD不需要额外解析库；仅PDF需要可选pypdf。拒绝安装、没有权限或安装失败都可以继续其他支持格式。DOC、RTF、ODT可用已有本地软件导出DOCX/TXT；扫描PDF和图片另需本地OCR及核对。

可先做不读取正文的环境检查：

```bash
python3 contract-review-cn/scripts/pipeline.py doctor --input /path/to/contract.pdf
```

doctor输出当前Python解释器、库是否可用、文件序号与建议。不要把READY理解为已成功提取。混合输入中未处理文件会保留缺口，最终不能宣称完整审核；全部不可处理时提示转换或按需安装。[完整格式矩阵及引导规则](../contract-review-cn/references/input-formats.md)

必需：合同文件或附件。支持UTF-8 TXT/MD、DOCX、可提取文字的PDF。附录、补充协议、技术/质量文件一并提供，标明主合同和版本。

建议补充：我方角色、签署/履行日期、适用法域、交易背景、不可接受条件、企业规则。未知时可先做中立或部分审核，关键事实保留待确认。

```text
审核 ~/Downloads/采购合同.pdf 和 ~/Downloads/质量附件.docx。
我方是采购方，准备本月签署，交易在中国大陆。
重点关注验收、付款、转包和退出安排。
```

用户无需配置专家或写JSON。主agent负责交易画像、组队、调度及汇总。

## 实际需要用户参与的步骤

1. 提供正确路径与相关附件。
2. 本地核对提取完整性和脱敏，尤其姓名、地址、商业秘密、表格和扫描页；确认后才分发脱敏包。
3. 回答影响结论的必要事实问题。
4. 阅读意见，交由法务或业务负责人决定修改与签署。

扫描件、手写和复杂版面需要本地OCR/视觉核对；当前没有无人介入的扫描件全自动审核承诺。

## 工具与模型

| 能力 | 用途 | 缺失时 |
|---|---|---|
| 本地文件及Python | 提取、脱敏、映射、校验 | 先修复环境 |
| 子agent工具 | 真正独立、分批并行审核 | 明确待执行；不把串行扮演称并行 |
| Web搜索与页面读取 | 核验官方法源及版本 | 依据保持未核验，不能完整通过 |
| 浏览器/CDP | 普通读取不足的动态网页 | 按需兜底，不是必装组件 |
| 本地OCR/文档工具 | 扫描件、复杂版面、修订稿 | 报告相应缺口 |

模型由宿主提供。本仓库没有托管推理API、模型账户或额度；费用、上下文和并发由环境决定。没有跨模型质量/成本排名，不能保证更换模型效果相同。

## 离线演示的输出

```bash
python3 demo.py --out review-runs/my-first-demo
```

只能运行固定原创样例，不接受用户合同参数。生成 `REPORT.md`、`summary.json`、`redacted.txt`、`public/bundle.json` 和私有映射。已有目录拒绝覆盖；真实合同不能套用演示的自动测试确认。

真实审核默认输出脱敏报告，恢复身份仅按用户要求在本地执行。不要将 `private/` 上传Git或发给外部模型。

[返回首页](../README.md) · [底层workflow](../contract-review-cn/references/workflow.md)
