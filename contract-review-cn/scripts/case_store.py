"""Local case tree for AI IDEs. CLI emits identifiers/counts only, never raw metadata."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

import pipeline as p

FORMAT = "contract-case-store-v1"


def identifier(value: str) -> str:
    p.require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value), "INVALID_IDENTIFIER")
    return value


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe(path: Path) -> Path:
    """Reject existing symlinks at every ancestor, including an explicit root."""
    for part in (path, *path.parents):
        p.require(not part.is_symlink(), "STORE_SYMLINK_REJECTED")
    return path


def root_path(value: Path | None) -> Path:
    # abspath keeps symlinks visible; resolve would hide them before checking.
    return safe(Path(os.path.abspath((value or Path.cwd() / "contract-cases").expanduser())))


def read(path: Path) -> dict:
    value = p.read_json(safe(path))
    p.require(isinstance(value, dict), "STORE_RECORD_INVALID")
    p.require(value.get("digest") == p.digest({k: v for k, v in value.items() if k != "digest"}), "STORE_RECORD_CHANGED")
    return value


def record(path: Path, value: dict) -> None:
    safe(path)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({**value, "digest": p.digest(value)}, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        # Atomic publication with no overwrite, even if another writer won.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(root: Path):
    p.require(read(root / "store.json").get("format") == FORMAT, "STORE_FORMAT_INVALID")
    lock = safe(root / ".write-lock")
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise p.GateError("STORE_BUSY_OR_STALE_LOCK") from None
    try:
        yield
    finally:
        lock.rmdir()


def case_path(root: Path, case: str) -> Path:
    return safe(root / "private" / "cases" / identifier(case))


def case_exists(root: Path, case: str) -> Path:
    folder = case_path(root, case)
    p.require(read(folder / "case.json").get("case_id") == case, "CASE_ID_MISMATCH")
    return folder


@contextmanager
def staged(parent: Path, destination: Path):
    safe(parent)
    safe(destination)
    p.require(not destination.exists(), "RECORD_ALREADY_EXISTS")
    temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=parent))
    try:
        yield temporary
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def initialize(root: Path) -> dict:
    p.require(not root.exists(), "STORE_ALREADY_EXISTS")
    root.parent.mkdir(parents=True, exist_ok=True)
    with staged(root.parent, root) as temporary:
        (temporary / "private" / "cases").mkdir(mode=0o700, parents=True)
        (temporary / "private").chmod(0o700)
        p.write_new(temporary / ".gitignore", "*\n!.gitignore\n")
        record(temporary / "store.json", {"format": FORMAT, "created_at": stamp()})
    return {"status": "STORE_CREATED"}


def create_case(root: Path, case: str, metadata: Path | None = None) -> dict:
    destination = case_path(root, case)
    details = p.read_json(metadata) if metadata else {}
    p.require(isinstance(details, dict), "CASE_METADATA_INVALID")
    with locked(root), staged(destination.parent, destination) as temporary:
        for name in ("contracts", "snapshots", "reviews"):
            (temporary / name).mkdir(mode=0o700)
        record(temporary / "case.json", {"case_id": case, "created_at": stamp(), "metadata": details})
    return {"status": "CASE_CREATED", "case_id": case}


def version(root: Path, case: str, contract: str, revision: str) -> tuple[dict, Path]:
    folder = case_exists(root, case) / "contracts" / identifier(contract) / "versions" / identifier(revision)
    data = read(folder / "version.json")
    p.require(data.get("contract_id") == contract and data.get("version_id") == revision, "VERSION_ID_MISMATCH")
    filename = data.get("file")
    p.require(isinstance(filename, str) and re.fullmatch(r"original\.[a-z0-9]{1,10}", filename), "VERSION_PATH_INVALID")
    source = safe(folder / filename)
    p.require(hashlib.sha256(source.read_bytes()).hexdigest() == data["sha256"], "ORIGINAL_CHANGED")
    return data, source


def import_version(root: Path, case: str, contract: str, revision: str, source: Path,
                   parent: str | None = None) -> dict:
    identifier(contract)
    identifier(revision)
    if parent is not None:
        identifier(parent)
    suffix = source.suffix.lower()
    p.require(re.fullmatch(r"\.[a-z0-9]{1,10}", suffix), "FILE_EXTENSION_REQUIRED")
    content = source.read_bytes()
    p.require(content, "EMPTY_ORIGINAL")
    with locked(root):
        folder = safe(case_exists(root, case) / "contracts" / contract / "versions")
        if folder.exists():
            existing = [child for child in folder.iterdir() if not child.name.startswith(".")]
            p.require(not existing or parent is not None, "VERSION_PARENT_REQUIRED")
        if parent:
            version(root, case, contract, parent)
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        folder.parent.chmod(0o700)
        with staged(folder, folder / revision) as temporary:
            filename = "original" + suffix
            fd = os.open(temporary / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
            record(temporary / "version.json", {"contract_id": contract, "version_id": revision,
                   "parent": parent, "received_at": stamp(), "source_name": source.name,
                   "sha256": hashlib.sha256(content).hexdigest(), "file": filename})
    return {"status": "VERSION_IMPORTED", "case_id": case, "contract_id": contract, "version_id": revision}


def snapshot(root: Path, case: str, snapshot_id: str) -> dict:
    data = read(case_exists(root, case) / "snapshots" / (identifier(snapshot_id) + ".json"))
    p.require(data.get("snapshot_id") == snapshot_id, "SNAPSHOT_ID_MISMATCH")
    for contract, member in data["members"].items():
        data_version, _ = version(root, case, contract, member["version_id"])
        p.require(data_version["digest"] == member["version_digest"], "SNAPSHOT_VERSION_CHANGED")
    return data


def make_snapshot(root: Path, case: str, snapshot_id: str, members: list[str],
                  group: str = "main", parent: str | None = None) -> dict:
    identifier(snapshot_id)
    identifier(group)
    with locked(root):
        folder = case_exists(root, case)
        if parent:
            p.require(snapshot(root, case, parent)["group_id"] == group, "SNAPSHOT_GROUP_MISMATCH")
        entries = {}
        for member in members:
            contract, separator, revision = member.partition("=")
            p.require(separator and contract not in entries, "SNAPSHOT_MEMBERS_INVALID")
            data, _ = version(root, case, contract, revision)
            entries[contract] = {"version_id": revision, "version_digest": data["digest"]}
        p.require(entries, "SNAPSHOT_EMPTY")
        record(folder / "snapshots" / (snapshot_id + ".json"), {"snapshot_id": snapshot_id,
               "group_id": group, "parent": parent, "created_at": stamp(), "members": entries})
    return {"status": "SNAPSHOT_CREATED", "case_id": case, "snapshot_id": snapshot_id, "members": len(entries)}


def prepare_review(root: Path, case: str, snapshot_id: str, review_id: str,
                   baseline: str | None = None, entities: Path | None = None) -> dict:
    identifier(review_id)
    with locked(root):
        folder = case_exists(root, case)
        new = snapshot(root, case, snapshot_id)
        old = snapshot(root, case, baseline) if baseline else None
        p.require(old is None or old["group_id"] == new["group_id"], "SNAPSHOT_GROUP_MISMATCH")
        inputs, pairs, indices = [], [], {}
        for side, snap in (("before", old), ("after", new)):
            for contract, member in sorted((snap or {}).get("members", {}).items()):
                _, source = version(root, case, contract, member["version_id"])
                inputs.append(source)
                indices[side, contract] = len(inputs)
        if old is not None:
            pairs = [{"before": indices.get(("before", contract)), "after": indices.get(("after", contract))}
                     for contract in sorted(set(old["members"]) | set(new["members"]))]
        destination = folder / "reviews" / review_id
        with staged(destination.parent, destination) as temporary:
            run = temporary / "run"
            with redirect_stdout(io.StringIO()):
                p.prepare(argparse.Namespace(run=run, input=inputs, entities=entities,
                          comparison_pairs=pairs if old is not None else None))
            bundle = p.read_json(run / "private" / "candidate.json")
            record(temporary / "binding.json", {"case_id": case, "review_id": review_id,
                   "snapshot_id": snapshot_id, "snapshot_digest": new["digest"],
                   "baseline_id": baseline, "baseline_digest": old["digest"] if old else None,
                   "input_digest": bundle["input_digest"],
                   "comparison_digest": bundle.get("comparison", {}).get("comparison_digest"),
                   "created_at": stamp()})
    return {"status": "PREPARED_PRIVATE", "case_id": case, "review_id": review_id,
            "run": str(destination / "run"), "local_review_required": True}


def index(root: Path, case: str | None = None) -> dict:
    """Derived index: never exposes titles, source names, metadata or raw texts."""
    with locked(root):
        ids = [identifier(case)] if case else sorted(child.name for child in safe(root / "private" / "cases").iterdir()
                                                   if not child.name.startswith("."))
        cases = []
        for case_id in ids:
            folder = case_exists(root, case_id)
            contracts, snapshots, reviews = [], [], []
            for child in sorted(safe(folder / "contracts").iterdir()):
                versions = []
                for revision in sorted(safe(child / "versions").iterdir()):
                    if revision.name.startswith("."):
                        continue
                    data, _ = version(root, case_id, child.name, revision.name)
                    versions.append({"version_id": revision.name, "parent": data["parent"], "sha256": data["sha256"]})
                contracts.append({"contract_id": child.name, "versions": versions})
            for child in sorted(safe(folder / "snapshots").glob("*.json")):
                data = snapshot(root, case_id, child.stem)
                snapshots.append({key: data[key] for key in ("snapshot_id", "group_id", "parent", "members")})
            for child in sorted(safe(folder / "reviews").iterdir()):
                if child.name.startswith("."):
                    continue
                data = read(child / "binding.json")
                p.require(data["case_id"] == case_id and data["review_id"] == child.name, "REVIEW_ID_MISMATCH")
                p.require(data["snapshot_digest"] == snapshot(root, case_id, data["snapshot_id"])["digest"], "REVIEW_SNAPSHOT_CHANGED")
                if data["baseline_id"]:
                    p.require(data["baseline_digest"] == snapshot(root, case_id, data["baseline_id"])["digest"], "REVIEW_BASELINE_CHANGED")
                candidate = p.read_json(safe(child / "run" / "private" / "candidate.json"))
                p.check_bundle(candidate)
                p.require(data["input_digest"] == candidate["input_digest"] and data["comparison_digest"] ==
                          candidate.get("comparison", {}).get("comparison_digest"), "REVIEW_INPUT_CHANGED")
                published = safe(child / "run" / "public" / "bundle.json")
                if published.exists():
                    public = p.read_json(published)
                    p.check_bundle(public)
                    p.require(public["input_digest"] == data["input_digest"], "REVIEW_PUBLIC_CHANGED")
                reviews.append({**{key: data[key] for key in ("review_id", "snapshot_id", "baseline_id", "input_digest")},
                                "run": str(child / "run"), "published_bundle_present": published.exists(),
                                "reports": report_index(child / "run", data)})
            cases.append({"case_id": case_id, "contracts": contracts, "snapshots": snapshots, "reviews": reviews})
    return {"status": "INDEX_VERIFIED", "cases": cases}


def report_index(run: Path, binding: dict) -> list[dict]:
    """Index only immutable reports whose content and input bindings still match."""
    result = []
    versions = safe(run / "reports" / "versions")
    if not versions.exists():
        return result
    for folder in sorted(versions.iterdir()):
        p.require(re.fullmatch(r"v\d{6,}", folder.name), "REPORT_VERSION_INVALID")
        manifest = p.read_json(safe(folder / "manifest.json"))
        p.require(manifest["revision"] == int(folder.name[1:]) and
                  manifest["input_digest"] == binding["input_digest"] and
                  manifest.get("comparison_digest") == binding["comparison_digest"], "REPORT_BINDING_CHANGED")
        report = safe(folder / "report.md")
        results = p.read_json(safe(folder / "results.json"))
        p.require(hashlib.sha256(report.read_bytes()).hexdigest() == manifest["report_sha256"] and
                  p.digest(results) == manifest["results_digest"], "REPORT_CONTENT_CHANGED")
        result.append({"revision": manifest["revision"], "report": str(report),
                       "declared_depth_status": manifest["declared_depth_status"],
                       "legal_signoff": manifest["legal_signoff"]})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Default: current working directory / contract-cases")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    listing = commands.add_parser("list")
    listing.add_argument("--case")
    create = commands.add_parser("create")
    create.add_argument("--case", required=True)
    create.add_argument("--metadata", type=Path)
    imp = commands.add_parser("import")
    imp.add_argument("--case", required=True)
    imp.add_argument("--contract", required=True)
    imp.add_argument("--version", required=True)
    imp.add_argument("--input", type=Path, required=True)
    imp.add_argument("--parent")
    snap = commands.add_parser("snapshot")
    snap.add_argument("--case", required=True)
    snap.add_argument("--snapshot", required=True)
    snap.add_argument("--member", action="append", required=True)
    snap.add_argument("--group", default="main")
    snap.add_argument("--parent")
    review = commands.add_parser("prepare")
    review.add_argument("--case", required=True)
    review.add_argument("--snapshot", required=True)
    review.add_argument("--review", required=True)
    review.add_argument("--baseline")
    review.add_argument("--entities", type=Path)
    args = parser.parse_args()
    try:
        root = root_path(args.root)
        if args.command == "init":
            outcome = initialize(root)
        elif args.command == "create":
            outcome = create_case(root, args.case, args.metadata)
        elif args.command == "import":
            outcome = import_version(root, args.case, args.contract, args.version, args.input, args.parent)
        elif args.command == "snapshot":
            outcome = make_snapshot(root, args.case, args.snapshot, args.member, args.group, args.parent)
        elif args.command == "prepare":
            outcome = prepare_review(root, args.case, args.snapshot, args.review, args.baseline, args.entities)
        else:
            outcome = index(root, args.case)
        print(json.dumps(outcome, ensure_ascii=False))
        return 0
    except p.GateError as exc:
        print(json.dumps({"status": "FAILED", "code": str(exc)}))
        return 2
    except Exception:
        print('{"status":"FAILED","code":"STORE_IO_OR_SCHEMA_ERROR"}')
        return 3


if __name__ == "__main__":
    sys.exit(main())
