"""Generate a result card from completed experiments, never infer missing success."""
import argparse
import json
from pathlib import Path
from common import dump


def complete_evaluation(result, expected, adapter):
    return (result.get('gate') == 'PASS_CONTROLLED_BENCHMARK'
            and result.get('rows') == expected['rows']
            and result.get('data_digest') == expected['digest']
            and result.get('mode') == 'hybrid'
            and result.get('adapter') == str(adapter))


def main(root, candidate, output):
    experiments = [
        ("规则基线／开发集", "rules-v2-dev"), ("原模型＋规则／开发集", "base-dev"),
        ("第一轮微调＋规则／开发集", "v1-dev"), ("第二轮微调＋规则／开发集", "v2-dev"),
        ("第三轮微调＋规则／开发集", "v3-dev"),
        ("第四轮末步＋规则／开发集", "v4-dev"),
        ("候选＋规则／开发集", candidate + "-dev"),
        ("候选／原创保留测试", candidate + "-test"), ("候选／公开中文对照", candidate + "-public"),
        ("候选／固定挑战集", candidate + "-challenge"),
        ("规则基线／公开中文对照", "rules-public-exact"),
    ]
    lines = ["# 契衡本地隐私模型：实验结果", "", "仅使用原创虚构合同及公开合成数据；未读取用户合同。", "",
             "| 实验 | 样本 | 分类字符召回率 | 分类字符精确率 | 格式有效率 | 分类整段无遗漏率 | 状态 |",
             "|---|---:|---:|---:|---:|---:|---|"]
    results = {}
    for label, name in experiments:
        path = root / "evals" / name / "metrics.json"
        if not path.exists():
            lines.append(f"| {label} | — | — | — | — | — | 未完成 |")
            continue
        r = json.loads(path.read_text())
        results[name] = r
        lines.append(f"| {label} | {r['rows']} | {r['char_recall']:.2%} | {r['char_precision']:.2%} | "
                     f"{r['valid_output_rate']:.2%} | {r['document_no_miss_rate']:.2%} | {r['gate']} |")
    required = [candidate + suffix for suffix in ("-dev", "-test", "-public", "-challenge")]
    original = json.loads((root / 'data/v3/manifest.json').read_text())['files']
    public = json.loads((root / 'data/openpii-zh-v4/manifest.json').read_text())
    challenge = json.loads((root / 'data/challenge-v1/manifest.json').read_text())
    expected = {'-dev': original['dev'], '-test': original['test'],
                '-public': {'rows': public['rows'], 'digest': public['row_digest']},
                '-challenge': challenge}
    qualified = all(candidate + suffix in results and complete_evaluation(
        results[candidate + suffix], manifest, root / 'adapters' / candidate)
        for suffix, manifest in expected.items())
    lines += ["", "## 资格结论", "",
              "达到所列受控数据集的数值门槛；不代表真实合同或零泄露保证。" if qualified else
              "**未达到完整验收门槛，不建议开始用户真实合同验证。** 缺失或失败的测试不能由其他测试集的高分抵消。",
              "", "门槛：字符召回≥99%、精确率≥95%、无无效输出；模型不得改写合同。", "",
              "整段无遗漏率单独披露，不是零泄露认证。报告还核对冻结数据的完整样本量、摘要和候选身份。", "",
              "## 训练与资源", ""]
    for version in dict.fromkeys(("v1", "v2", "v3", "v4", candidate)):
        folder = root / "adapters" / version
        path = folder / "status.json"
        if path.exists():
            status = json.loads(path.read_text())
            size = (folder / "adapters.safetensors").stat().st_size if (folder / "adapters.safetensors").exists() else 0
            lines.append(f"- {version}：{status['status']}；{status['elapsed_seconds']:.1f}秒；"
                         f"峰值内存{status.get('peak_memory_gb', 0):.2f}GB；适配器{size/1e6:.2f}MB。")
    selection = root / 'adapters' / candidate / 'selection.json'
    if selection.exists():
        selected = json.loads(selection.read_text())
        lines.append(f"- 候选{candidate}来自{selected['parent']}第{selected['step']}步，按完整开发集最低验证损失选定，未用保留测试选型。不是额外训练轮次。")
    lines += ["", "## 候选分类型遗漏与误报", "",
              "计数单位为带类型的原文字符。同一位置类型错判会同时产生遗漏和误报。", "",
              "| 数据集 | 类型 | 漏掉字符 | 多报字符 |", "|---|---|---:|---:|"]
    for name in required:
        if name not in results:
            continue
        for kind, counts in results[name]['by_type'].items():
            if counts['fn'] or counts['fp']:
                lines.append(f"| {name} | {kind} | {counts['fn']} | {counts['fp']} |")
    lines += ["", "## 不计类型的实际遮盖覆盖", "",
              "将所有预测片段视为遮盖范围，检查金标准敏感字符是否仍有残留。它区分类型错判和漏遮，不代替原验收门槛，也不证明金标准没有漏标。", "",
              "| 数据集 | 字符遮盖召回率 | 无残留片段比例 | 未遮盖敏感字符 |", "|---|---:|---:|---:|"]
    for name in required:
        path = root / 'evals' / name / 'coverage-audit.json'
        if path.exists():
            r = json.loads(path.read_text())
            lines.append(f"| {name} | {r['untyped_coverage_recall']:.2%} | {r['document_no_unmasked_gold_rate']:.2%} | {r['unmasked_characters']} |")
    lines += ["", "## 推理实测", "",
              "以下延迟为本次短片段推理，不能直接外推到整份合同；内存为MLX分配峰值，不含全部系统占用。", ""]
    for name in required:
        if name in results:
            r = results[name]
            lines.append(f"- {name}：P50 {r['latency_p50_seconds']:.3f}秒，P95 {r['latency_p95_seconds']:.3f}秒；"
                         f"MLX峰值 {r.get('peak_memory_gb', 0):.2f}GB。")
            if 'entity_full_coverage_recall' in r:
                lines.append(f"  实体完整覆盖率 {r['entity_full_coverage_recall']:.2%}"
                             f"（{r['fully_covered_entity_count']}/{r['gold_entity_count']}），允许覆盖片段比金标准更宽；过宽部分仍计入字符误报。")
    lines += ["", "## 证据与限制", "",
              "- 训练/验证loss、超参数、模型与数据摘要、原始预测保存在本地artifacts/privacy中；该目录不进入Git。",
              "- 原创数据按措辞家族和实体库存划分，但由同一开发者生成，不是独立人工金标准。",
              "- 公开对照采用数据供应方标注，存在类别粒度和质量限制；只评其已覆盖类型。",
              "- 公开中文对照仅评PERSON、PHONE、EMAIL、ID、ADDRESS、ACCOUNT，不证明其他类别识别能力。来源Ai4Privacy / Ai Suisse SA，供应方声明CC BY 4.0。",
              "- 固定挑战集含20条手写虚构片段，不参与训练；同样不是独立人工金标准。字符指标不能替代逐文档无遗漏指标。",
              "- 低loss不等于无遗漏。未做操作系统级强隔离验收；本实验不授予自动外发任何内容的权限。",
              "- 保留测试集被用于指导后续迭代时必须降级为开发资料，另建独立保留集。", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    dump(root / "qualification" / (candidate + ".json"), {"candidate": candidate,
         "qualified_on_controlled_benchmarks": qualified, "certifies_zero_leakage": False,
         "required": required, "results": results})
    print(json.dumps({"report": str(output), "qualified_on_controlled_benchmarks": qualified}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("artifacts/privacy"))
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.root, args.candidate, args.output)
