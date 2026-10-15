from __future__ import annotations
import hashlib,json,re
from pathlib import Path
class EvaluationError(ValueError): pass
def sha256_file(path):
 h=hashlib.sha256(); f=Path(path).open('rb')
 while chunk:=f.read(1048576): h.update(chunk)
 f.close(); return h.hexdigest()
def load_jsonl(path):
 out=[]
 for n,line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(),1):
  if line.strip():
   try: row=json.loads(line)
   except json.JSONDecodeError as e: raise EvaluationError(f'BAD_JSON_LINE_{n}') from e
   if not isinstance(row,dict): raise EvaluationError('ROW_SCHEMA')
   out.append(row)
 return out
def _ids(rows,label):
 if not rows: raise EvaluationError('EMPTY_DATASET')
 seen=set()
 for row in rows:
  ident=row.get('id')
  if type(ident) is not str or not ident: raise EvaluationError(f'{label}_ID_INVALID')
  if ident in seen: raise EvaluationError(f'{label}_ID_DUPLICATE')
  seen.add(ident)
 return seen
def _spans(row,key):
 raw=row.get(key)
 if key not in row or not isinstance(raw,list): raise EvaluationError(f'{key.upper()}_MISSING')
 out=[]
 for item in raw:
  if not isinstance(item,dict): raise EvaluationError(f'{key.upper()}_SPAN_SCHEMA')
  a,b=item.get('start'),item.get('end')
  if type(a) is not int or type(b) is not int or a<0 or b<=a or b>len(row['text']): raise EvaluationError(f'{key.upper()}_SPAN_RANGE')
  if any(a<y and b>x for x,y in out): raise EvaluationError(f'{key.upper()}_SPAN_OVERLAP')
  out.append((a,b))
 return out
def validate_manifest(manifest,paths):
 if not isinstance(manifest,dict): raise EvaluationError('MANIFEST_SCHEMA')
 for key,path in paths.items():
  expected=manifest.get(key)
  if type(expected) is not str or len(expected)!=64: raise EvaluationError(f'MANIFEST_{key.upper()}_MISSING')
  if sha256_file(path)!=expected: raise EvaluationError(f'MANIFEST_{key.upper()}_MISMATCH')
def evaluate(data,predictions,protocol=None):
 if _ids(data,'DATA')!=_ids(predictions,'PREDICTION'): raise EvaluationError('ID_SET_MISMATCH')
 by={r['id']:r for r in predictions}; records=[]; g=c=x=blocked=0
 for row in data:
  text=row.get('text')
  if type(text) is not str: raise EvaluationError('TEXT_SCHEMA')
  if 'gold_spans' not in row:
   entities=row.get('entities')
   if not isinstance(entities,list): raise EvaluationError('GOLD_SPANS_MISSING')
   spans=[]
   for entity in entities:
    literal=(entity.get('text') or entity.get('value')) if isinstance(entity,dict) else None
    if not isinstance(literal,str) or not literal: raise EvaluationError('ENTITIES_SCHEMA')
    matches=list(re.finditer(re.escape(literal),text))
    if not matches: raise EvaluationError('ENTITY_NOT_IN_SOURCE')
    spans.extend({'start':m.start(),'end':m.end()} for m in matches)
   row={**row,'gold_spans':spans}
  gs=_spans(row,'gold_spans')
  for item,(a,b) in zip(row['gold_spans'],gs):
   if item.get('text') is not None and text[a:b]!=item['text']: raise EvaluationError('GOLD_TEXT_SPAN_MISMATCH')
  gold=set(i for a,b in gs for i in range(a,b)); pred=by[row['id']]
  if type(pred.get('blocked')) is not bool: raise EvaluationError('BLOCKED_SCHEMA')
  if pred['blocked'] and pred.get('predicted_spans'): raise EvaluationError('BLOCKED_WITH_COVERAGE')
  if pred['blocked'] and any(pred.get(k,0) != 0 for k in ('covered_chars','extra_chars')): raise EvaluationError('BLOCKED_WITH_COVERAGE')
  if 'gold_chars' in pred and pred['gold_chars'] != len(gold): raise EvaluationError('GOLD_COUNT_MISMATCH')
  if 'scoring_scope' in row and row['scoring_scope'] != [0,len(text)]: raise EvaluationError('PARTIAL_SCOPE_UNSUPPORTED')
  level=pred.get('verification_level', protocol or 'blocked-unscored' if pred['blocked'] else 'native-span-v1'); cov=set()
  if not pred['blocked'] and 'predicted_spans' in pred:
   for a,b in _spans({'text':text,'predicted_spans':pred['predicted_spans']},'predicted_spans'): cov.update(range(a,b))
   hit,miss,extra=len(gold&cov),len(gold-cov),len(cov-gold)
  elif not pred['blocked']:
   level='legacy-counts-v1'; vals=[pred.get(k) for k in ('covered_chars','missed_chars','extra_chars')]
   if any(type(v) is not int or v<0 for v in vals) or vals[0]+vals[1]!=len(gold) or vals[2]>len(text)-len(gold): raise EvaluationError('LEGACY_COUNT_NOT_CONSERVATIVE')
   hit,miss,extra=vals
  else: hit,miss,extra=0,len(gold),0
  g+=len(gold);c+=hit;x+=extra;blocked+=int(pred['blocked']); redacted=pred.get('redacted_text') or ''; preservation=(redacted==row.get('preserve_text') if 'preserve_text' in row else True) and all(v in redacted for v in row.get('preserve_literals',[]));records.append({'id':row['id'],'verification_level':level,'blocked':pred['blocked'],'missed_chars':miss,'extra_chars':extra,'preservation_passed':preservation})
 return {'rows':len(data),'blocked':blocked,'gold_chars':g,'covered_chars':c,'extra_chars':x,'char_recall':c/g if g else 1.0,'char_precision':c/(c+x) if c+x else (1.0 if not g else 0.0),'blocked_rate':blocked/len(data),'delivered_with_residual':sum(r['missed_chars']>0 and not r['blocked'] for r in records),'preservation_failed':sum(not r['preservation_passed'] and not r['blocked'] for r in records),'verification_level':sorted({r['verification_level'] for r in records}),'production_qualified':False,'records':records,'notes':['Offline prediction scoring only; no model inference.','Native metrics validate spans only, not redacted output content.','Legacy counts are not independently reconstructed.','Development evaluation does not imply production qualification.']}
