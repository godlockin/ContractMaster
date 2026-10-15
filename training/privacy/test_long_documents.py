import unittest
import json
import redact_local

from normalized_view import canonical_view
from partition import PartitionError, partition_view


class FakeTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return messages[0]["content"] + "|" + messages[1]["content"]

    def encode(self, text):
        return list(text)


class LongDocumentTests(unittest.TestCase):
    def setUp(self):
        self.tokenizer = FakeTokenizer()
        self.view = canonical_view("前文。联系人：张三。" * 30)

    def test_overlap_prompt_is_bounded_and_core_covers_exactly(self):
        parts = partition_view(self.view, self.tokenizer, "SYS", max_input=32,
                               max_output=4, max_total=2000, overlap=6)
        self.assertEqual("".join(p.text[p.core_start:p.core_end] for p in parts), self.view.text)
        for p in parts:
            self.assertLessEqual(len(self.tokenizer.encode("SYS|" + p.text)), 32)

    def test_total_chunks_and_invalid_bool(self):
        with self.assertRaises(PartitionError):
            partition_view(self.view, self.tokenizer, "SYS", max_input=32, max_output=4,
                           max_total=40)
        with self.assertRaisesRegex(PartitionError, "MAX_CHUNKS_EXCEEDED"):
            partition_view(self.view, self.tokenizer, "SYS", max_input=32, max_output=4,
                           max_total=2000, max_chunks=1, overlap=0)
        with self.assertRaisesRegex(PartitionError, "INVALID_PARTITION_BUDGET"):
            partition_view(self.view, self.tokenizer, "SYS", max_input=True)

    def test_unicode_positions_reversible(self):
        source = "甲😀Ａ́乙"
        view = canonical_view(source)
        self.assertEqual("甲😀A乙", view.text)
        self.assertEqual(source[view.positions[2][0]:view.positions[2][1]], "Ａ́")

    def _run(self, source, answer, **kw):
        calls = []
        def generate(model, tokenizer, prompt, max_tokens, verbose=False):
            calls.append(prompt)
            return answer(prompt) if callable(answer) else answer
        return redact_local.redact_text(source, object(), self.tokenizer, generate,
                                        max_input=600, max_output=100,
                                        max_total=50000, max_chunks=64, **kw), calls

    def test_long_model_public_amount_is_kept(self):
        result, calls = self._run("公开报价300万元。" * 120, '[{"text":"300万元","type":"SECRET"}]')
        self.assertGreater(len(calls), 1)
        self.assertIn("300万元", result["redacted_text"])

    def test_long_model_empty_still_rules_fullwidth_phone(self):
        result, calls = self._run("背景。" * 120 + "电话：１３８００１３８０００", "[]")
        self.assertGreater(len(calls), 1)
        self.assertIn("⟦PHONE_", result["redacted_text"])

    def test_custom_alias_is_projected(self):
        result, calls = self._run("背景。" * 120 + "Alpha（以下简称甲方）计划", "[]",
                              custom=[{"text":"Alpha计划", "type":"PROJECT"}])
        self.assertGreater(len(calls), 1)
        self.assertIn("⟦PROJECT_", result["redacted_text"])

    def test_middle_malformed_chunk_aborts(self):
        count = [0]
        def answer(_):
            count[0] += 1
            return "{" if count[0] == 2 else "[]"
        with self.assertRaisesRegex(ValueError, "MODEL_OUTPUT_BLOCKED"):
            self._run("背景。" * 300, answer)

    def test_long_model_fullwidth_org_and_split_name(self):
        source = "背景。" * 120 + "签约主体：ＡＢＣ有限公司；联系人：张 / 三"
        result, calls = self._run(
            source,
            lambda prompt: json.dumps([
                {"text": "ABC有限公司", "type": "ORG"},
                {"text": "张 / 三", "type": "PERSON"}] if ("ABC" in prompt or "张" in prompt) else [], ensure_ascii=False))
        self.assertGreater(len(calls), 1)
        self.assertNotIn("ＡＢＣ有限公司", result["redacted_text"])

    def test_boundary_budget_failure(self):
        with self.assertRaises(ValueError):
            redact_local.redact_text("很长。" * 40, object(), self.tokenizer,
                                     lambda *a, **k: "[]", max_input=600,
                                     max_output=100, max_total=10)

    def test_truncated_output_at_limit_aborts(self):
        with self.assertRaisesRegex(ValueError, "MODEL_OUTPUT_TRUNCATED"):
            redact_local.redact_text("短文本", object(), self.tokenizer,
                                     lambda *a, **k: "x" * 20, max_input=1000,
                                     max_output=20)


if __name__ == "__main__":
    unittest.main()
