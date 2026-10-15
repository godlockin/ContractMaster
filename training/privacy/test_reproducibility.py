from pathlib import Path
import json
import unittest

from reproducibility import snapshot, restore_check
from reproducibility import validate_adapter_chain, sha256


class ReproducibilityTests(unittest.TestCase):
  def _temp(self):
    import tempfile
    holder = tempfile.TemporaryDirectory()
    self.addCleanup(holder.cleanup)
    return Path(holder.name)

  def test_snapshot_and_tamper_detection(self):
    tmp_path = self._temp()
    root = tmp_path / "repo"; root.mkdir()
    (root / "training").mkdir(); lock = root / "requirements-lock.txt"; lock.write_text("mlx==0.0\n")
    data = root / "canonical"; data.mkdir()
    (data / "rows.jsonl").write_text('{"text":"public synthetic","status":"accepted"}\n{"text":"withheld","status":"rejected"}\n')
    out = tmp_path / "snap"
    args = type("Args", (), {"root": root, "output": out, "lock": lock, "config": [], "data": [data], "model": None,
        "model_profile": None, "framework": "test", "model_source": "synthetic", "model_revision": "r1",
        "quantization": None, "tokenizer": "test-tokenizer", "adapter_parent": None, "include_weights": False})()
    manifest = snapshot(args)
    assert manifest["data"]["status_counts"]["rejected"] == 1
    self.assertTrue(manifest["privacy"]["contents_embedded"])
    restore_check(out / "manifest.json")
    (out / "payload" / "canonical" / "rows.jsonl").write_text("tampered\n")
    with self.assertRaisesRegex(ValueError, "SNAPSHOT_HASH_MISMATCH"):
        restore_check(out / "manifest.json")


  def test_weights_excluded_by_default(self):
    tmp_path = self._temp()
    root = tmp_path / "repo"; root.mkdir(); weights = root / "adapters.safetensors"; weights.write_bytes(b"weights")
    out = tmp_path / "snap"
    args = type("Args", (), {"root": root, "output": out, "lock": root / "missing.lock", "config": [], "data": [], "model": str(weights),
        "model_profile": None, "framework": "mlx", "model_source": "local", "model_revision": "r", "quantization": "4bit",
        "tokenizer": "tok", "adapter_parent": None, "include_weights": False})()
    assert not snapshot(args)["files"]


  def test_preflight_requires_parent_hash_and_base_identity(self):
    tmp_path = self._temp()
    model = tmp_path / "model.json"; model.write_text(json.dumps({"repo": "public/model", "revision": "r1"}))
    adapter = tmp_path / "a" / "adapters.safetensors"; adapter.parent.mkdir(); adapter.write_bytes(b"a")
    (adapter.parent / "provenance.json").write_text(json.dumps({"model": {"repo": "public/model", "revision": "r1"},
        "adapter_sha256": sha256(adapter)}))
    validate_adapter_chain(adapter, model)
    (adapter.parent / "provenance.json").write_text(json.dumps({"model": {"revision": "r1"}, "adapter_sha256": sha256(adapter)}))
    with self.assertRaisesRegex(ValueError, "MODEL_IDENTITY_INCOMPLETE|ADAPTER_BASE_IDENTITY"):
        validate_adapter_chain(adapter, model)

  def test_inventory_rejects_external_and_parent_symlink(self):
    root = self._temp(); outside = self._temp(); secret = outside / "secret.json"; secret.write_text("x")
    with self.assertRaisesRegex(ValueError, "EXTERNAL_PATH_REJECTED"):
        from reproducibility import inventory
        inventory([secret], root)
    link = root / "linkdir"; link.symlink_to(outside, target_is_directory=True)
    with self.assertRaisesRegex(ValueError, "EXTERNAL_PATH_REJECTED"):
        inventory([link / "secret.json"], root)


if __name__ == "__main__":
    unittest.main()
