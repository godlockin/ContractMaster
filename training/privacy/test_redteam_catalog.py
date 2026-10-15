"""Guard scoring against adversarial fixtures with misleading gold labels."""
import html
import unittest

from redteam_attack_catalog import specifications


class AttackCatalogTests(unittest.TestCase):
    def test_wrapper_instructions_are_not_sensitive_gold(self):
        wrappers = {'markdown_emphasis', 'markdown_link', 'quoted_surface',
                    'html_tag_wrap', 'field_scatter', 'negation_reversal',
                    'prompt_injection', 'bidi_controls'}
        for spec in specifications():
            if spec['category'] in wrappers:
                self.assertEqual(spec['clean_entities'], spec['attack_entities'])

    def test_html_attack_really_encodes_entity(self):
        for spec in specifications():
            if spec['category'] == 'html_entity':
                for (original, kind), (encoded, encoded_kind) in zip(
                        spec['clean_entities'], spec['attack_entities']):
                    self.assertNotEqual(original, encoded)
                    self.assertEqual(html.unescape(encoded), original)
                    self.assertEqual(kind, encoded_kind)

    def test_financial_controls_retain_units_without_sensitive_gold(self):
        controls = [s for s in specifications() if s['category'] == 'finance_semantics']
        self.assertTrue(controls)
        for spec in controls:
            self.assertNotEqual(spec['clean'], spec['attack'])
            self.assertFalse(spec['attack_entities'])
            for literal in spec['preserve']:
                self.assertIn(literal, spec['attack'])
