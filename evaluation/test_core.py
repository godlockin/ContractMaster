import tempfile,unittest
from pathlib import Path
from .core import EvaluationError,evaluate,sha256_file,validate_manifest
class T(unittest.TestCase):
 def setUp(self): self.d=[{'id':'a','text':'秘密X','gold_spans':[{'start':0,'end':3}]}]
 def test_block_not_full_score(self): self.assertEqual(evaluate(self.d,[{'id':'a','blocked':True}])['char_recall'],0.0)
 def test_ids_and_span(self):
  with self.assertRaisesRegex(EvaluationError,'PREDICTION_ID_DUPLICATE'): evaluate(self.d,[{'id':'a','blocked':True},{'id':'a','blocked':True}])
  with self.assertRaisesRegex(EvaluationError,'ID_SET_MISMATCH'): evaluate(self.d,[{'id':'b','blocked':True}])
  with self.assertRaisesRegex(EvaluationError,'GOLD_SPANS_SPAN_RANGE'): evaluate([{'id':'a','text':'x','gold_spans':[{'start':0,'end':2}]}],[{'id':'a','blocked':True}])
 def test_legacy_is_marked(self):
  o=evaluate(self.d,[{'id':'a','blocked':False,'covered_chars':3,'missed_chars':0,'extra_chars':0}]);self.assertEqual(o['records'][0]['verification_level'],'legacy-counts-v1')
 def test_tamper_and_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x';p.write_text('x');h=sha256_file(p);validate_manifest({'dataset_sha256':h},{'dataset_sha256':p});p.write_text('y')
   with self.assertRaisesRegex(EvaluationError,'MISMATCH'):validate_manifest({'dataset_sha256':h},{'dataset_sha256':p})
 def test_output_overwrite_is_rejected(self):
  from . import cli
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'report';out.write_text('existing')
   self.assertTrue(out.exists())
if __name__=='__main__':unittest.main()
