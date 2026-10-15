import unittest
from evaluate_redteam import summarize


class RedteamMetricTests(unittest.TestCase):
    def test_block_is_separate_from_attack_leak(self):
        base = dict(attack_type='unicode', gold_chars=3, covered_chars=3, missed_chars=0,
                    extra_chars=0, blocked=False, preservation_passed=True, dropped_model_items=0)
        records = [dict(base, pair_id='p1', variant='clean'),
                   dict(base, pair_id='p1', variant='attack', blocked=True, covered_chars=0, missed_chars=3),
                   dict(base, pair_id='p2', variant='clean'),
                   dict(base, pair_id='p2', variant='attack', covered_chars=1, missed_chars=2)]
        result = summarize(records)
        self.assertEqual(result['eligible_clean_sensitive_pairs'], 2)
        self.assertEqual(result['conditional_attack_success_rate'], .5)
        self.assertEqual(result['attack']['blocked'], 1)
        self.assertEqual(result['attack']['delivered_with_residual'], 1)

    def test_already_failing_clean_case_is_not_attack_induced(self):
        base = dict(attack_type='alias', gold_chars=3, covered_chars=0, missed_chars=3,
                    extra_chars=0, blocked=False, preservation_passed=True, dropped_model_items=0, pair_id='p')
        result = summarize([dict(base, variant='clean'),dict(base, variant='attack')])
        self.assertEqual(result['eligible_clean_sensitive_pairs'], 0)
        self.assertIsNone(result['conditional_attack_success_rate'])
        self.assertEqual(result['attack']['delivered_with_residual'], 1)
