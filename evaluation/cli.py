from __future__ import annotations
import argparse,json
import re,hashlib
from pathlib import Path
from .core import EvaluationError,evaluate,load_jsonl,sha256_file,validate_manifest
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--predictions',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists(): raise EvaluationError('OUTPUT_EXISTS')
 m=json.loads(a.manifest.read_text()); required=['model_id','base_repo','base_revision','base_weights_sha256','adapter_sha256','runtime_sha256','dataset_id','dataset_role','protocol','dataset_sha256','predictions_sha256']
 if any(type(m.get(k)) is not str or not m.get(k) for k in required if k not in ('runtime_sha256','dataset_sha256','predictions_sha256')): raise EvaluationError('MANIFEST_REQUIRED_FIELDS')
 for key in ('base_weights_sha256','adapter_sha256'):
  if not re.fullmatch(r'[0-9a-f]{64}',m.get(key,'')): raise EvaluationError('MANIFEST_HASH_INVALID')
 if not isinstance(m.get('runtime_sha256'),dict) or not m['runtime_sha256']: raise EvaluationError('MANIFEST_RUNTIME_EMPTY')
 if any(not isinstance(v,str) or not re.fullmatch(r'[0-9a-f]{64}',v) for v in m['runtime_sha256'].values()): raise EvaluationError('MANIFEST_RUNTIME_HASH_INVALID')
 if m.get('protocol') not in ('legacy-counts-v1','native-span-v1'): raise EvaluationError('MANIFEST_PROTOCOL_INVALID')
 validate_manifest(m,{'dataset_sha256':a.data,'predictions_sha256':a.predictions})
 out=evaluate(load_jsonl(a.data),load_jsonl(a.predictions),m['protocol']);out['manifest']=m;out['manifest_sha256']=sha256_file(a.manifest);out['dataset_sha256']=sha256_file(a.data);out['predictions_sha256']=sha256_file(a.predictions);out['suite_version']='1.0.0';out['scorer_files_sha256']={str(p):sha256_file(p) for p in (Path(__file__),Path(__file__).with_name('core.py'),Path(__file__).with_name('__init__.py'))}
 if any(r['verification_level'] != m['protocol'] for r in out['records']): raise EvaluationError('MANIFEST_PROTOCOL_MISMATCH')
 a.output.parent.mkdir(parents=True,exist_ok=True)
 with a.output.open('x',encoding='utf-8') as stream: stream.write(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'status':'EVALUATION_COMPLETE','rows':out['rows']}))
if __name__=='__main__':
 try: main()
 except (EvaluationError,OSError,json.JSONDecodeError) as e: print(json.dumps({'status':'EVALUATION_FAILED','reason':str(e)}));raise SystemExit(2)
