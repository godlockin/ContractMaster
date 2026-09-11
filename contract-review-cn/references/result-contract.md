# 专家结果契约

合同版本比较模式另须提交 comparison_digest 和逐项 change_reviews，字段、枚举及完整性门禁见 [修改审核](change-review.md)。普通单版本审核无需这些字段。

新任务按[双组协议](dual-team.md)，每份角色结果增加team和first_pass，R1声明与深度记录摘要绑定。下例为通用字段示意，不是完整的双组结果。

`bundle.json` 包含 `input_digest`、六个 `roles`、五个 `levels`、`documents`、`segments`。原件名称用 DOC0001 等替代。segments 的 start/end 是**各文档脱敏文本**坐标；风险引用必须按这些坐标，不能用模型 token 索引。

bundle.roles 是不可修改的六基础角色；实际审核阵容来自最新 expert-plan，允许专项角色。每个 JSON 文件对应一个计划角色，携带 plan_digest（完整计划 JSON 的 pipeline.digest）；计划变更后必须真实复核并重新确认，不能仅替换摘要：

```json
{
  "role": "legal",
  "input_digest": "公共包内的值",
  "plan_digest": "最新专家计划的摘要",
  "global_context_reviewed": true,
  "global_note": "已检查的跨条款关系及仍待确认问题",
  "reviews": [
    {"segment_id": "DOC0001-S00001", "levels": ["char", "word", "sentence", "paragraph", "context"], "review_note": "具体检查记录，包含否定词、期限、责任等结论"}
  ],
  "findings": [
    {
      "id": "legal-001",
      "severity": "high",
      "category": "liability",
      "evidence": [{"segment_id": "DOC0001-S00001", "start": 0, "end": 4, "quote": "精确原文"}],
      "risk": "风险机制及触发条件",
      "impact": "对我方后果",
      "suggestion": "可执行修订方向或替换条文",
      "basis": [{"status": "unverified", "title": "拟核实的规范", "article": "待核实", "url": "", "checked_at": "", "applicability": "待确认适用条件"}],
      "confidence": "medium",
      "questions": ["必要事实缺口"]
    }
  ]
}
```

severity 为 critical/high/medium/low/info；confidence 为 high/medium/low；basis status 为 verified/unverified/not_applicable。无法律依据需要时用空 basis，并在 risk 中明确商业/文本判断。verified 必须有 HTTPS 法源 URL、检查日期、条号/定位和适用说明；仅结构验证通过不证明法源真实。

verified 的 URL 必须含有效主机，checked_at 使用 YYYY-MM-DD。申报完整深度时，每条 verified basis 还须含 `source_id`，关联 audit-depth.sources 中的 verified 来源；title、url、checked_at 与来源一致，article 属于该来源 articles。缺少关联或字段不匹配会保持 PARTIAL_AUDIT；历史结果可作初稿，但需补齐关联后再申报完整。

每个风险至少一条精确证据；跨条款冲突至少两条。完全缺失的条款引用相关义务、合同目录或末尾，并在 risk 中写明“缺失项，无直接原文”。不能捏造缺失条款 quote。

validate 拒绝：未知/重复角色，陈旧摘要，缺段/多段/重复片段，缺审核层次，空审核说明，未做全局轮，重复风险 ID，空风险字段，无效级别，越界或不匹配引文。报告保留全量原始 findings，人工合并不得抹去来源。覆盖矩阵是**自报审核覆盖**，不能证明真实认知覆盖或原件 OCR 100% 正确。

## 未决问题及已解决记录

`questions` 默认表示未决事项。保留历史问题时，可追加 `question_resolutions:[{question:"与questions中完全相同的问题",status:"resolved",reason:"解决理由",evidence_refs:["有效source ID或segment ID"]}]`。每个问题最多一条，必须有引用；不能仅写resolved布尔值。深度校验读取真实finding，未核验basis及未解决questions都阻断完整状态；有证据的解决声明仍需专业复核。

本地泄漏门禁递归检查解码后JSON所有字符串值和键，包含嵌套和转义字符；只能查出词典已有实体，不等于穷尽敏感信息。
