import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
class C(unittest.TestCase):
 def make(self,protocol='native-span-v1',tamper=None):
  d=Path(tempfile.mkdtemp()); data=d/'data.jsonl';pred=d/'pred.jsonl';man=d/'manifest.json';out=d/'out.json'
  data.write_text(json.dumps({'id':'a','text':'secret','gold_spans':[{'start':0,'end':6}]})+'\n')
  p={'id':'a','blocked':False,'predicted_spans':[{'start':0,'end':6}]} if protocol.startswith('native') else {'id':'a','blocked':True,'verification_level':'legacy-counts-v1','covered_chars':0,'missed_chars':6,'extra_chars':0}
  pred.write_text(json.dumps(p)+'\n')
  h=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest()
  m={'model_id':'m','base_repo':'repo','base_revision':'r','base_weights_sha256':'a'*64,'adapter_sha256':'b'*64,'runtime_sha256':{'core.py':'c'*64},'dataset_id':'d','dataset_role':'dev','protocol':protocol,'dataset_sha256':h(data),'predictions_sha256':h(pred)}
  if tamper=='pred': pred.write_text('x')
  if tamper=='adapter': m['adapter_sha256']='bad'
  if tamper=='protocol': m['protocol']='bad'
  man.write_text(json.dumps(m));return d,data,pred,man,out
 def run_cli(self,*args): return subprocess.run([sys.executable,'-m','evaluation.cli',*map(str,args)],capture_output=True,text=True)
 def test_valid_native(self):
  d,data,pred,man,out=self.make();self.addCleanup(lambda: __import__('shutil').rmtree(d,ignore_errors=True));r=self.run_cli('--data',data,'--predictions',pred,'--manifest',man,'--output',out);self.assertEqual(r.returncode,0)
 def test_valid_legacy_blocked_protocol(self):
  d,data,pred,man,out=self.make('legacy-counts-v1');self.addCleanup(lambda: __import__('shutil').rmtree(d,ignore_errors=True));r=self.run_cli('--data',data,'--predictions',pred,'--manifest',man,'--output',out);self.assertEqual(r.returncode,0)
 def test_missing_model_bad_hash_unknown_protocol(self):
  for mode,needle in [('adapter','MANIFEST_HASH_INVALID'),('protocol','MANIFEST_PROTOCOL_INVALID')]:
   d,data,pred,man,out=self.make(tamper=mode);self.addCleanup(lambda d=d: __import__('shutil').rmtree(d,ignore_errors=True));r=self.run_cli('--data',data,'--predictions',pred,'--manifest',man,'--output',out);self.assertIn(needle,r.stdout)
  def test_missing_model_field(self):
   d,data,pred,man,out=self.make();self.addCleanup(lambda: __import__('shutil').rmtree(d,ignore_errors=True));m=json.loads(man.read_text());del m['model_id'];man.write_text(json.dumps(m));self.assertIn('MANIFEST_REQUIRED_FIELDS',self.run_cli('--data',data,'--predictions',pred,'--manifest',man,'--output',out).stdout)
  def test_dataset_hash_tamper(self):
   d,data,pred,man,out=self.make();self.addCleanup(lambda: __import__('shutil').rmtree(d,ignore_errors=True));data.write_text('tamper');self.assertIn('MISMATCH',self.run_cli('--data',data,'--predictions',pred,'--manifest',man,'--output',out).stdout)
 def test_prediction_hash_tamper(self):
  d,data,pred,man,out=self.make(tamper='pred');self.addCleanup(lambda: __import__('shutil').rmtree(d,ignore_errors=True));r=self.run_cli('--data',data,'--predictions',pred,'--manifest',man,'--output',out);self.assertIn('MISMATCH',r.stdout)
 def test_duplicate_output(self):
  d,data,pred,man,out=self.make();self.addCleanup(lambda: __import__('shutil').rmtree(d,ignore_errors=True));out.write_text('x');r=self.run_cli('--data',data,'--predictions',pred,'--manifest',man,'--output',out);self.assertIn('OUTPUT_EXISTS',r.stdout)
 def test_report_hash_fields(self):
  d,data,pred,man,out=self.make();self.addCleanup(lambda: __import__('shutil').rmtree(d,ignore_errors=True));self.assertEqual(self.run_cli('--data',data,'--predictions',pred,'--manifest',man,'--output',out).returncode,0);r=json.loads(out.read_text());self.assertEqual(r['manifest_sha256'],hashlib.sha256(man.read_bytes()).hexdigest());self.assertEqual(r['suite_version'],'1.0.0');self.assertIn('scorer_files_sha256',r)
if __name__=='__main__': unittest.main()
