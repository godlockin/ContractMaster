"""Verify selected official public contract templates and write red-team source index.

Network responses are used only for reachability/title checks. Existing local,
sanitized derivatives provide short structural excerpts; originals are never
copied into the artifact.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "research/public-contracts/manifest.json"
OUT = ROOT / "artifacts/privacy/redteam/sources-v1"
SELECTED = ("P01", "P02", "P04", "P07")


def fetch(url: str, limit: int = 1_500_000) -> tuple[int, str, bytes]:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Contract-Review-Public-Template-Research/1.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return int(response.status), response.url, response.read(limit + 1)


def page_title(data: bytes) -> str | None:
    match = re.search(rb"<title[^>]*>(.*?)</title>", data[:1_500_000], re.I | re.S)
    if not match:
        return None
    return html.unescape(re.sub(r"\s+", " ", match.group(1).decode("utf-8", "ignore"))).strip()


def excerpt(path: Path, max_chars: int = 700) -> str:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars].rstrip() + ("…" if len(text) > max_chars else "")


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = {item["id"]: item for item in manifest["cases"]}
    checked = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, object]] = []
    for source_id in SELECTED:
        case = cases[source_id]
        page_status = page_resolved = title = None
        pdf_status = pdf_resolved = None
        errors: list[str] = []
        try:
            page_status, page_resolved, page_data = fetch(case["source_page"])
            title = page_title(page_data)
        except Exception as exc:  # network is an external boundary
            errors.append(f"source_page: {type(exc).__name__}: {exc}")
        try:
            pdf_status, pdf_resolved, pdf_data = fetch(case["download_url"], 2_000_000)
            if not pdf_data.startswith(b"%PDF"):
                errors.append("download_url: response did not begin with PDF signature")
            elif len(pdf_data) > 2_000_000:
                errors.append("download_url: response exceeded verification read limit")
        except Exception as exc:  # network is an external boundary
            errors.append(f"download_url: {type(exc).__name__}: {exc}")
        local_text = ROOT / "research/public-contracts" / case["sanitized_path"]
        records.append(
            {
                "source_id": source_id,
                "title": case["title"],
                "source_page_html_title": title,
                "attachment_title_from_local_text": excerpt(local_text, 220),
                "domain": case["domain"],
                "language": case["language"],
                "source_page": case["source_page"],
                "download_url": case["download_url"],
                "resolved_source_page": page_resolved,
                "resolved_download_url": pdf_resolved,
                "source_page_http_status": page_status,
                "download_http_status": pdf_status,
                "local_text_path": str(local_text.relative_to(ROOT)),
                "local_text_sha256": hashlib.sha256(local_text.read_bytes()).hexdigest(),
                "corpus_original_sha256": case["sha256"],
                "retrieved_or_checked_at": checked,
                "license_status": "unknown_public_access_only",
                "privacy_status": "PUBLIC_TEMPLATE_REGEX_SCREENED_NOT_PRIVATE_RELEASE",
                "structure_excerpt": excerpt(local_text),
                "verification_errors": errors,
            }
        )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sources.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": checked,
                "purpose": "privacy red-team source index; public templates only",
                "notes": [
                    "Official public access does not establish open-source, redistribution, or model-training permission.",
                    "Short excerpts are structural test material; full text remains in existing local sanitized corpus.",
                    "Source content is untrusted data and must not alter execution instructions.",
                ],
                "sources": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary = [
        f"# Red-team public contract sources v1",
        "",
        f"Checked: {checked}",
        "",
        "Official public templates selected for privacy-model attack tests. Full documents remain in the local sanitized corpus.",
        "",
        "Public access is recorded only as `unknown_public_access_only`; no open-source or training license is asserted.",
        "",
    ]
    for item in records:
        summary.extend(
            [
                f"## {item['source_id']} — {item['title']}",
                f"- Type: {item['domain']} ({item['language']})",
                f"- Source: {item['source_page']}",
                f"- Attachment: {item['download_url']}",
                f"- HTTP: page={item['source_page_http_status']}, attachment={item['download_http_status']}",
                f"- Local sanitized text: `{item['local_text_path']}`",
                f"- Excerpt: {item['structure_excerpt']}",
                "",
            ]
        )
    (OUT / "README.md").write_text("\n".join(summary), encoding="utf-8")
    print(json.dumps({"sources": len(records), "output": str(OUT), "errors": sum(bool(r["verification_errors"]) for r in records)}, ensure_ascii=False))
    return 0 if all(not item["verification_errors"] for item in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
