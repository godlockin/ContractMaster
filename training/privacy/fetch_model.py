"""Resume pinned public weights; verify upstream LFS SHA256 before use."""
from __future__ import annotations
import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path

REPO = "mlx-community/Qwen3-1.7B-4bit"
REVISION = "3b1b1768f8f8cf8351c712464f906e86c2b8269e"


def main(root, repo=REPO, revision=REVISION, base_model="Qwen/Qwen3-1.7B"):
    root.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true&expand=false"
    with urllib.request.urlopen(url, timeout=30) as response:
        files = json.load(response)
    records = []
    for info in files:
        if info["type"] != "file" or info["path"].startswith("."):
            continue
        target = root / info["path"]
        expected = info["size"]
        for attempt in range(8):
            have = target.stat().st_size if target.exists() else 0
            if have == expected:
                break
            if have > expected:
                raise ValueError("MODEL_FILE_OVERSIZE")
            request = urllib.request.Request(
                f"https://huggingface.co/{repo}/resolve/{revision}/{info['path']}?download=true&offset={have}",
                headers={"Range": f"bytes={have}-"})
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    partial = response.status == 206
                    if partial and not response.headers.get("Content-Range", "").startswith(f"bytes {have}-"):
                        raise ValueError("BAD_RESUME_RANGE")
                    remaining = expected - have if partial else expected
                    announced = response.headers.get("Content-Length")
                    if announced is not None and int(announced) > remaining:
                        raise ValueError("BAD_RESUME_LENGTH")
                    with target.open("ab" if partial else "wb") as stream:
                        written = 0
                        while written < remaining and (chunk := response.read(min(1024*1024, remaining - written))):
                            stream.write(chunk)
                            written += len(chunk)
                        if written != remaining:
                            raise ValueError("MODEL_RESPONSE_TRUNCATED")
            except (OSError, TimeoutError):
                if attempt == 7:
                    raise
                time.sleep(2)
        if not target.exists() or target.stat().st_size != expected:
            raise ValueError("MODEL_DOWNLOAD_INCOMPLETE")
        checksum = hashlib.sha256()
        with target.open("rb") as stream:
            while chunk := stream.read(1024*1024):
                checksum.update(chunk)
        if info.get("lfs", {}).get("oid") and checksum.hexdigest() != info["lfs"]["oid"]:
            raise ValueError("MODEL_UPSTREAM_CHECKSUM_MISMATCH")
        records.append({"file": info["path"], "sha256": checksum.hexdigest(), "bytes": expected,
                        "upstream_lfs_sha256": info.get("lfs", {}).get("oid")})
    (root / "verified-download.json").write_text(json.dumps({"repo": repo, "revision": revision,
         "base_model": base_model, "license": "apache-2.0", "files": records}, indent=2))
    print(json.dumps({"status": "MODEL_VERIFIED", "bytes": sum(x["bytes"] for x in records)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo", default=REPO)
    parser.add_argument("--revision", default=REVISION)
    parser.add_argument("--base-model", default="Qwen/Qwen3-1.7B")
    args = parser.parse_args()
    main(args.output, args.repo, args.revision, args.base_model)
