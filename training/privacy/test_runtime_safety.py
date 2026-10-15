"""Focused runtime safety checks for local privacy redaction."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import types
import unittest
import sys
import subprocess
import hashlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_status
import redact_local
from privacy_config import init, validate


class RuntimeSafetyTests(unittest.TestCase):
    def test_adapter_tamper_is_rejected_after_available_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); model = root/'model'; adapter = root/'adapter'
            model.mkdir(); adapter.mkdir()
            files = []
            for name in ('config.json', 'tokenizer.json', 'model.safetensors'):
                raw = b'fixture'
                (model/name).write_bytes(raw)
                files.append({'file':name, 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()})
            (model/'verified-download.json').write_text(json.dumps({'revision':'r1', 'files':files}))
            (adapter/'adapters.safetensors').write_bytes(b'fixture-adapter')
            (adapter/'adapter_config.json').write_text(json.dumps({'fine_tune_type':'lora', 'model':'model'}))
            (adapter/'provenance.json').write_text(json.dumps({'model':{'revision':'r1'},
                'adapter_sha256':hashlib.sha256(b'fixture-adapter').hexdigest()}))
            with patch.object(model_status, '_has_module', return_value=True):
                self.assertEqual(model_status.check_model(model, adapter)['status'], 'AVAILABLE')
                (adapter/'adapters.safetensors').write_bytes(b'changed')
                self.assertEqual(model_status.check_model(model, adapter)['reason'], 'ADAPTER_CHECKSUM_MISMATCH')

    def test_cli_bad_policy_never_logs_private_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, policy = root/'input.txt', root/'policy.json'
            source.write_text('仅为虚构合同测试。', encoding='utf-8')
            policy.write_text('{"entities": SECRET_DO_NOT_LOG}', encoding='utf-8')
            policy.chmod(0o600)
            result = subprocess.run([sys.executable, str(Path(redact_local.__file__)),
                '--input', str(source), '--config', str(policy), '--output', str(root/'out'),
                '--backend', 'rules'], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr, '')
            self.assertNotIn('SECRET_DO_NOT_LOG', result.stdout)
            self.assertEqual(json.loads(result.stdout)['status'], 'LOCAL_REDACTION_FAILED')
            self.assertFalse((root/'out').exists())

    def test_dictionary_entry_survives_guardrails_and_unmatched_is_ignored(self):
        custom = [{"text": "北岑计划", "type": "PROJECT"},
                  {"text": "不在原文", "type": "PROJECT"}]
        result = redact_local._rule_redact("项目代号北岑计划。", custom)
        self.assertNotIn("北岑计划", result["redacted_text"])
        self.assertEqual(result["entity_count"], 1)

    def test_rules_backend_does_not_probe_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / "input.txt", Path(tmp) / "out"
            source.write_text("联系人张三。", encoding="utf-8")
            args = types.SimpleNamespace(input=source, output=output,
                model=Path(tmp) / "missing-model", adapter=Path(tmp) / "missing-adapter",
                backend="rules", config=None, entities=None, self_test=False,
                max_input=128, max_output=64)
            with patch.object(redact_local, "check_model", side_effect=AssertionError("probe")):
                with contextlib.redirect_stdout(io.StringIO()):
                    redact_local.main(args)
            self.assertTrue((output / "redacted.txt").is_file())

    def test_policy_permissions_are_700_and_600(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "case"
            init(root)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual((root / "privacy-policy.json").stat().st_mode & 0o777, 0o600)
            root.chmod(0o755)
            self.assertEqual(validate(root / "privacy-policy.json")["reason"],
                             "CONFIG_DIRECTORY_PERMISSION_MUST_BE_700")

    def test_manifest_rejects_path_escape_without_leaking_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); model = root / "model"; adapter = root / "adapter"
            model.mkdir(); adapter.mkdir()
            (model / "verified-download.json").write_text(json.dumps({
                "revision": "r", "files": [{"file": "../secret", "bytes": 1, "sha256": "0" * 64}]}))
            status = model_status.check_model(model, adapter)
            self.assertEqual(status["status"], "INTEGRITY_FAILED")
            self.assertNotIn("secret", json.dumps(status))


if __name__ == "__main__":
    unittest.main()
