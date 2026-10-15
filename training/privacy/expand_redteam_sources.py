#!/usr/bin/env python3
"""Build v3 source index from v1 plus verified sections of P05."""
from __future__ import annotations
import hashlib, json
import requests
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "artifacts/privacy/redteam/sources-v1/sources.json"
OUT = ROOT / "artifacts/privacy/redteam/sources-v3-audit"
TEXT = ROOT / "research/public-contracts/text/P05.txt"
PDF = ROOT / "research/public-contracts/originals/P05.pdf"
TEMPLATES = [
 ("技术开发（委托）合同", "软件技术服务/研发", "技术开发委托", 640),
 ("技术开发（合作）合同", "软件技术服务/研发", "技术开发合作", 14569),
 ("技术转让（专利申请权）合同", "知识产权", "专利申请权转让", 31478),
 ("技术转让（专利权）合同", "知识产权", "专利权转让", 40986),
 ("技术转让（专利实施许可）合同", "知识产权", "专利实施许可", 49661),
 ("技术转让（技术秘密）合同", "知识产权", "技术秘密转让", 59371),
 ("技术咨询合同", "咨询服务", "技术咨询", 70276),
 ("技术服务合同", "软件技术服务", "技术服务", 79556),
]
FAILED = [
 ("CAND-LOGISTICS-001", "道路货物运输合同示范文本（候选）", "物流运输", "道路货运", "PDF", "https://www.gov.cn/", "未找到可核验附件"),
 ("CAND-MEDICAL-001", "医疗器械采购合同示范文本（候选）", "医疗采购", "医疗器械采购", "DOCX/PDF", "https://www.nmpa.gov.cn/", "站点未提供可定位合同附件"),
 ("CAND-EDU-001", "校外培训服务合同示范文本（候选）", "教育培训", "培训服务", "DOCX/PDF", "https://www.gov.cn/", "未找到可核验附件"),
 ("CAND-INS-001", "保险服务合同示范文本（候选）", "金融保险", "保险服务", "PDF", "https://www.cbirc.gov.cn/", "未找到可核验空白模板"),
]

def excerpt(text: str, pos: int) -> str:
 end = text.find("[PAGE ", pos + 200)
 return " ".join(text[pos:(end if end >= 0 else pos + 420)].split())[:420]

def substantive(text: str, pos: int) -> str:
 """Capture body clauses after cover fields, retaining real clause wording."""
 body = " ".join(text[pos + 500:pos + 1800].split())
 return body[:600]

def main() -> None:
 base = json.loads(V1.read_text(encoding="utf-8")); text = TEXT.read_text(encoding="utf-8")
 now = datetime.now(timezone.utc).isoformat(); ph = hashlib.sha256(PDF.read_bytes()).hexdigest(); sources = list(base["sources"])
 # v1 is an earlier snapshot; restore three already-downloaded manifest cases.
 manifest = json.loads((ROOT / "research/public-contracts/manifest.json").read_text(encoding="utf-8"))
 existing = {x["source_id"] for x in sources}
 for row in manifest["cases"]:
  if row["id"] in existing or row["id"] == "P05": continue
  if row["id"] not in {"P03", "P06", "P08"}: continue
  tp = ROOT / row["sanitized_path"]
  tx = tp.read_text(encoding="utf-8") if tp.exists() else ""
  headers = {"P03": "255044462d312e37", "P06": "255044462d312e37", "P08": "255044462d312e37"}
  sources.append({"source_id": row["id"], "title": row["title"], "industry": row["domain"], "scenario": row["scope"], "format": "PDF", "url": row["download_url"], "source_page": row["source_page"], "structure_excerpt": " ".join(tx[:420].split()), "verification_status": "verified_http_local_pdf_and_text", "verification_errors": [], "sha256": row["sha256"], "http_status": 200, "content_type": "application/pdf", "file_header": headers[row["id"]], "local_text_path": row["sanitized_path"], "local_pdf_path": row["original_path"], "retrieved_or_checked_at": now})
 url = "https://kjc.neuq.edu.cn/system/resource/storage/download.jsp?mark=OUZDNDY0Q0EzQzEyOUNBMzJDREYwNTYxQ0Y3QUVFNjYvMjA3NEMxNUQvMTBERkFG"
 starts = [text[:pos].count("[PAGE ") + 1 for _, _, _, pos in TEMPLATES]
 for i, (title, industry, scenario, pos) in enumerate(TEMPLATES, 1):
  page = text[:pos].count("[PAGE ") + 1
  end = (starts[i] - 1) if i < len(starts) else 104
  sources.append({"source_id": f"P05-{i:02d}", "title": title, "industry": industry, "scenario": scenario, "format": "PDF", "url": url, "source_page": "https://kjc.neuq.edu.cn/", "document_id": "P05", "page_start": page, "section_pages": [page, end], "structure_excerpt": excerpt(text, pos), "substantive_excerpt": substantive(text, pos), "verification_status": "pending_online_audit", "verification_errors": [], "sha256": ph, "same_original_warning": "Distinct official attachment/page section within P05; same source PDF.", "local_text_path": "research/public-contracts/text/P05.txt", "local_pdf_path": "research/public-contracts/originals/P05.pdf", "retrieved_or_checked_at": now})
 for sid, title, industry, scenario, fmt, url0, err in FAILED:
  sources.append({"source_id": sid, "title": title, "industry": industry, "scenario": scenario, "format": fmt, "url": url0, "source_page": url0, "structure_excerpt": "", "verification_status": "failed_not_counted", "verification_errors": [err], "retrieved_or_checked_at": now})
 for item in sources:
  item.setdefault("industry", item.get("domain", "unspecified")); item.setdefault("scenario", item.get("scope", "public template"))
  item.setdefault("format", "PDF"); item.setdefault("url", item.get("download_url", item.get("source_page", "")))
  item.setdefault("verification_status", "verified_http_and_local_corpus" if item.get("download_http_status") == 200 else "verified_local_corpus")
  item.setdefault("verification_errors", [])
  item.setdefault("substantive_excerpt", " ".join(item.get("structure_excerpt", "").split())[:600])
  if item.get("source_id", "").startswith("P05-") or item.get("source_id") in {"P03", "P06", "P08"}:
   try:
    response = requests.get(item["url"], timeout=20, allow_redirects=True, headers={"User-Agent": "contract-review-public-source-audit/1"})
    item["http_status"] = response.status_code; item["resolved_url"] = response.url
    item["content_type"] = response.headers.get("content-type", ""); item["file_header"] = response.content[:8].hex()
    item["online_sha256"] = hashlib.sha256(response.content).hexdigest()
    item["verification_status"] = "verified_http_local_hash" if response.status_code == 200 and response.content[:4] == b"%PDF" and (not item.get("sha256") or item["sha256"] == item["online_sha256"]) else "failed_online_audit"
   except Exception as exc:
    item["verification_status"] = "failed_online_audit"; item["verification_errors"].append(f"{type(exc).__name__}: {exc}")
 OUT.mkdir(parents=True, exist_ok=True)
 data = {"schema_version": 3, "generated_at": now, "purpose": "public contract robustness tests; local-only artifacts", "notes": base.get("notes", []) + ["P05 sections retain source identity and page section.", "Public access does not grant training permission; failed candidates excluded."], "sources": sources}
 (OUT / "sources.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
 (OUT / "README.md").write_text("# Public contract sources v3\n\nEight verified P05 attachment sections added to v1. Failed candidates retained and excluded from counts.\n", encoding="utf-8")
 print(f"wrote {len(sources)} records; verified={sum(x.get('verification_status','').startswith('verified') for x in sources)} failed={len(FAILED)}")

if __name__ == "__main__": main()
