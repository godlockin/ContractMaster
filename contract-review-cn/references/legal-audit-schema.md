# 本地合同审计台账 schema

`scripts/legal_audit.py` 只记录本地审计台账结构，不判断法律效力、不验签、不计算法定日期。每条记录必须包含：`schema_version`、`case_id`、`snapshot_digest`（64 位 hex）、`playbook_version`、`review_status`（`complete|partial`）、`input_digest`（64 位 hex 声明）、`context`、`playbook`、`document_chain`、`findings`、`obligations`。

最小合成记录：

```json
{
  "schema_version": "1.0",
  "case_id": "CASE-SYN-1",
  "snapshot_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "playbook_version": "PB-1",
  "review_status": "complete",
  "input_digest": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "context": {"our_position": "buyer", "jurisdiction": "CN", "audit_stage": "pre-sign", "known_gaps": []},
  "playbook": [{"id": "R-1", "side": "buyer", "preferred": "文本 A", "fallback": "文本 B", "red_line": "不得免除核心付款义务", "approval_role": "legal", "exception_allowed": false}],
  "document_chain": [{"id": "D-1", "version": "1", "status": "effective", "effective_date": "2026-01-01", "supersedes": null, "evidence_refs": ["E-1"]}],
  "findings": [{"id": "F-1", "clause": "2.1", "doc_refs": ["D-1"], "category": "commercial", "severity": "low", "risk": "价格口径不清", "impact": "结算争议", "proposed_text": "", "fallback": "", "decision": "accepted", "unresolved": false, "rule_id": "R-1", "exception_approval": "none"}],
  "obligations": [{"id": "O-1", "doc_id": "D-1", "clause": "3.1", "due_date": "2026-02-01", "notice_method": "email", "day_basis": "calendar days", "owner": "buyer", "status": "open"}],
  "evidence_disclaimer": "Approval evidence is self-reported; no signature verification or legal-effect determination."
}
```

运行（`SKILL_DIR` 为技能目录绝对路径）：

```text
python3 "$SKILL_DIR/scripts/legal_audit.py" init --output audit.json
python3 "$SKILL_DIR/scripts/legal_audit.py" check --input audit.json --output check-dir
python3 "$SKILL_DIR/scripts/legal_audit.py" report --input audit.json --output report-dir
```

输出状态只有 `WORKFLOW_READY` 与 `PARTIAL`。`WORKFLOW_READY` 只表示本台账结构门禁通过，不表示现有 pipeline 审核完成、法律意见成立或可以签署；缺口、未决风险、规则例外审批、证据不足均保持 `PARTIAL`。`report-dir` 是本地私有目录，含 `report.md`、`report.json`、`manifest.json`，须经既有 pipeline 复核和脱敏后再交付。
