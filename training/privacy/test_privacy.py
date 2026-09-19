import contextlib
import io
import json
import sys
import types
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common import parse, parse_tolerant, spans, rows
from evaluate import score, rule_entities
from prepare_data import build
from report import complete_evaluation
from coverage_audit import audit
from guardrails import entities as fallback_entities, resolve, filter_items
from model_status import check_model
from privacy_config import init as init_privacy_config, validate as validate_privacy_config
from redact_local import _custom_entities, _rule_redact
import redact_local


class PrivacyExperimentTests(unittest.TestCase):
    def test_generation_split_integrity_and_gold_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "data"
            with contextlib.redirect_stdout(io.StringIO()):
                build(root, 640)
            sets = {split: rows(root / f"{split}.jsonl") for split in ("train", "dev", "test")}
            hashes = set()
            families = {}
            for split, examples in sets.items():
                families[split] = {r["family"] for r in examples}
                for row in examples:
                    self.assertNotIn(row["text"], hashes)
                    hashes.add(row["text"])
                    spans(row["text"], row["entities"])
            self.assertFalse(families["train"] & families["test"])
            self.assertFalse((root / "mlx" / "test.jsonl").exists())
            self.assertEqual(len(rows(root / "mlx" / "train.jsonl")), 640)

    def test_invalid_or_invented_entity_rejected(self):
        for output in ('{"text":"张三"}', '[{"text":"李四","type":"PERSON"}]',
                       '[{"text":"张三","type":"UNSUPPORTED"}]', '解释：[]'):
            with self.assertRaises((ValueError, TypeError)):
                parse("联系人张三", output)

    def test_tolerant_parser_salvages_grounded_items(self):
        valid, dropped = parse_tolerant('联系人张三，邮箱a@sample.invalid',
            '[{"text":"张三","type":"PERSON"},{"text":"不存在","type":"PERSON"},{"text":"a@sample.invalid","type":"EMAIL"}]')
        self.assertEqual(valid, [{'text':'张三','type':'PERSON'},{'text':'a@sample.invalid','type':'EMAIL'}])
        self.assertEqual(dropped, 1)

    def test_all_occurrences_and_overlap_rules(self):
        self.assertEqual(spans("张三和张三", [{"text": "张三", "type": "PERSON"}]), {(0, 2, "PERSON"), (3, 5, "PERSON")})
        result = rule_entities("证件11010119900101001X")
        self.assertEqual(result, [{"text": "11010119900101001X", "type": "ID"}])

    def test_invalid_output_cannot_pass_even_when_rules_cover_everything(self):
        row = {"text": "张三", "entities": [{"text": "张三", "type": "PERSON"}],
               "predicted": [{"text": "张三", "type": "PERSON"}], "error": "INVALID", "seconds": .1}
        self.assertEqual(score([row])["gate"], "NOT_QUALIFIED")

    def test_missing_and_extra_characters_are_counted(self):
        row = {"text": "张三付款", "entities": [{"text": "张三", "type": "PERSON"}],
               "predicted": [{"text": "张三付款", "type": "PERSON"}], "error": None, "seconds": .1}
        result = score([row])
        self.assertEqual(result["char_recall"], 1)
        self.assertEqual(result["char_precision"], .5)
        self.assertEqual(result['entity_full_coverage_recall'], 1)
        short = score([{**row, 'predicted': [{'text': '张', 'type': 'PERSON'}]}])
        self.assertEqual(short['entity_full_coverage_recall'], 0)
        self.assertEqual(result["gate"], "NOT_QUALIFIED")

    def test_public_gold_keeps_original_coordinates_for_repeated_literals(self):
        row = {"text": "8号，8天", "entities": [{"text": "8", "type": "ADDRESS"}],
               "gold_spans": [[0, 1, "ADDRESS"]],
               "predicted": [{"text": "8", "type": "ADDRESS"}], "error": None, "seconds": .1}
        self.assertEqual(score([row])["char_precision"], .5)

    def test_qualification_rejects_subset_wrong_data_and_wrong_adapter(self):
        expected = {'rows': 100, 'digest': 'frozen-dataset'}
        result = {'gate': 'PASS_CONTROLLED_BENCHMARK', 'rows': 100,
                  'data_digest': 'frozen-dataset', 'mode': 'hybrid', 'adapter': 'candidate'}
        self.assertTrue(complete_evaluation(result, expected, Path('candidate')))
        for changes in ({'rows': 1}, {'data_digest': 'other'}, {'adapter': 'old'},
                        {'mode': 'rules'}, {'gate': 'NOT_QUALIFIED'}):
            self.assertFalse(complete_evaluation({**result, **changes}, expected, Path('candidate')))

    def test_wrong_type_is_distinct_from_unmasked_text(self):
        row = {'text': '北岑计划', 'entities': [{'text': '北岑计划', 'type': 'PROJECT'}],
               'predicted': [{'text': '北岑计划', 'type': 'SECRET'}], 'seconds': .1}
        self.assertEqual(score([row])['char_recall'], 0)
        self.assertEqual(audit([row])['untyped_coverage_recall'], 1)
        self.assertEqual(audit([{**row, 'predicted': []}])['untyped_coverage_recall'], 0)

    def test_local_guardrails_cover_explicit_formats_and_cues(self):
        text = '地址：杭州市青岚区星野路72号3层；项目代号白榆-07；保密底价人民币捌拾万元。'
        found = fallback_entities(text)
        self.assertIn({'text': '杭州市青岚区星野路72号3层', 'type': 'ADDRESS'}, found)
        self.assertIn({'text': '白榆-07', 'type': 'PROJECT'}, found)
        self.assertIn({'text': '人民币捌拾万元', 'type': 'SECRET'}, found)
        resolved = resolve(text, [{'text': '白榆-07', 'type': 'SECRET'}, {'text': '白榆-07', 'type': 'PROJECT'}])
        self.assertNotIn({'text': '白榆-07', 'type': 'SECRET'}, resolved)
        self.assertEqual(filter_items('付款金额100万元', [{'text':'100','type':'ID'}]), [])
        self.assertIn({'text':'6222000000000000123','type':'ACCOUNT'}, filter_items('账户6222000000000000123', [{'text':'6222000000000000123','type':'ACCOUNT'}]))

    def test_model_status_missing_is_safe_and_structured(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = check_model(Path(tmp) / 'missing-model', Path(tmp) / 'missing-adapter')
            self.assertEqual(status['status'], 'NOT_INSTALLED')
            self.assertNotIn('text', json.dumps(status, ensure_ascii=False))

    def test_model_status_rejects_adapter_revision_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / 'model'; adapter = root / 'adapter'
            model.mkdir(); adapter.mkdir()
            payload = b'local-model-metadata'
            (model / 'config.json').write_bytes(payload)
            import hashlib as _hashlib
            manifest = {'revision': 'rev-a', 'files': [{'file': 'config.json', 'bytes': len(payload),
                'sha256': _hashlib.sha256(payload).hexdigest()}]}
            (model / 'verified-download.json').write_text(json.dumps(manifest), encoding='utf-8')
            (adapter / 'adapters.safetensors').write_bytes(b'adapter')
            (adapter / 'adapter_config.json').write_text('{}', encoding='utf-8')
            (adapter / 'provenance.json').write_text(json.dumps({'model': {'revision': 'rev-b'}}), encoding='utf-8')
            status = check_model(model, adapter)
            self.assertEqual(status['status'], 'ADAPTER_MISMATCH')

    def test_privacy_config_init_and_permission_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'case'
            result = init_privacy_config(root)
            self.assertEqual(result['status'], 'INITIALIZED')
            config = root / 'privacy-policy.json'
            self.assertEqual(validate_privacy_config(config)['status'], 'VALID')
            config.chmod(0o644)
            self.assertEqual(validate_privacy_config(config)['reason'], 'CONFIG_PERMISSION_MUST_BE_600')

    def test_rules_failover_uses_custom_entities_without_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / 'privacy-policy.json'
            init_privacy_config(Path(tmp))
            policy.write_text(json.dumps({'policy_version': 1, 'entities': [
                {'value': '青岚数智有限公司', 'type': 'ORG'},
                {'value': '白榆-07', 'type': 'PROJECT'}]}), encoding='utf-8')
            policy.chmod(0o600)
            custom = _custom_entities(policy, None)
            result = _rule_redact('甲方青岚数智有限公司使用项目白榆-07。', custom)
            self.assertNotIn('青岚数智有限公司', result['redacted_text'])
            self.assertNotIn('白榆-07', result['redacted_text'])
            self.assertEqual(len(result['mapping']), 2)

    def test_auto_uses_local_model_when_capability_is_available(self):
        class FakeTokenizer:
            def apply_chat_template(self, messages, **kwargs):
                return 'prompt'
            def encode(self, prompt):
                return [1]

        def fake_load(*args, **kwargs):
            return object(), FakeTokenizer()

        def fake_generate(*args, **kwargs):
            return '[{"text":"张三","type":"PERSON"}]'

        fake_mlx = types.SimpleNamespace(load=fake_load, generate=fake_generate)
        with tempfile.TemporaryDirectory() as tmp, patch.object(
                redact_local, 'check_model', return_value={'status': 'AVAILABLE', 'reason': None}), \
                patch.dict(sys.modules, {'mlx_lm': fake_mlx}):
            source = Path(tmp) / 'input.txt'; output = Path(tmp) / 'output'
            source.write_text('联系人张三。', encoding='utf-8')
            args = types.SimpleNamespace(input=source, output=output,
                model=Path(tmp) / 'model', adapter=Path(tmp) / 'adapter', backend='auto',
                config=None, entities=None, self_test=False, max_input=128, max_output=64)
            with contextlib.redirect_stdout(io.StringIO()) as stream:
                redact_local.main(args)
            payload = json.loads(stream.getvalue())
            self.assertEqual(payload['backend'], 'local-model')
            self.assertNotIn('张三', (output / 'redacted.txt').read_text(encoding='utf-8'))


if __name__ == "__main__":
    unittest.main()
