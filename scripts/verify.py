"""One local/CI entry point. Only synthetic fixtures; any skipped test fails."""
from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUITES = ("contract-review-cn/scripts", "research/public-contracts/tools", "tests")


def run_suite(relative: str) -> dict:
    folder = ROOT / relative
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(folder))
    suite = unittest.TestLoader().discover(str(folder), pattern="test_*.py")
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        result = unittest.TextTestRunner(stream=buffer).run(suite)
    outcome = {"suite": relative, "tests": result.testsRun, "skipped": len(result.skipped),
               "status": "PASS" if result.wasSuccessful() and result.testsRun and not result.skipped else "FAILED"}
    if outcome["status"] != "PASS":
        # Tests use synthetic fixtures only; never point this runner at user runs.
        print(buffer.getvalue()[-4000:], file=sys.stderr)
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=SUITES)
    args = parser.parse_args()
    if args.suite:
        result = run_suite(args.suite)
        print(json.dumps(result))
        return 0 if result["status"] == "PASS" else 1
    try:
        version = importlib.metadata.version("pypdf")
    except importlib.metadata.PackageNotFoundError:
        print('{"status":"FAILED","code":"INSTALL_REQUIREMENTS_PDF"}')
        return 1
    expected = (ROOT / "requirements-pdf.txt").read_text().split("pypdf==", 1)[1].splitlines()[0].strip()
    if version != expected:
        print('{"status":"FAILED","code":"PDF_VERSION_MISMATCH"}')
        return 1
    checks = []
    with tempfile.TemporaryDirectory(prefix="contract-verify-") as temporary:
        copy = Path(temporary) / "contract-review-cn"
        shutil.copytree(ROOT / "contract-review-cn", copy, ignore=shutil.ignore_patterns("__pycache__"))
        commands = [(suite, [sys.executable, str(Path(__file__).resolve()), "--suite", suite]) for suite in SUITES]
        commands += [(name, [sys.executable, str(copy / "evals" / name)])
                     for name in ("run_acceptance.py", "score_review.py")]
        for name, command in commands:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
            if result.returncode:
                print(json.dumps({"status": "FAILED", "check": name}))
                print((result.stdout + result.stderr)[-4000:], file=sys.stderr)
                return 1
            checks.append(json.loads(result.stdout) if name in SUITES else {"check": name, "status": "PASS"})
    print(json.dumps({"status": "PASS", "python": sys.version.split()[0], "pypdf": version,
                      "tests": sum(check.get("tests", 0) for check in checks), "skipped": 0,
                      "checks": checks, "certifies_legal_quality": False}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print('{"status":"FAILED","code":"VERIFICATION_RUNTIME_ERROR"}')
        raise SystemExit(1)
