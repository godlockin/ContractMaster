"""Build small machine-checkable repair-v6 design sample; no historical data read."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from common import digest, messages, spans

CASES = [
 ('private_floor', '谈判记录：内部最低价为120万元；公开年度报价为300万元。', '谈判记录：合同服务费为120万元；公开年度报价为300万元。', [('120万元','SECRET')]),
 ('slash_person', '联系人魏 / 沐 / 樟负责签署；项目编号PX-17。', '联系人魏 / 沐 / 樟负责签署；订单金额120万元。', [('魏 / 沐 / 樟','PERSON')]),
 ('units', '月度结算为12万元，年度上限为144万元；内部底价为99万元。', '月度结算为12万元，年度上限为144万元；服务费为99万元。', [('99万元','SECRET')]),
 ('duplicate_value', '项目PX-120的预算为120万元，内部底价为80万元。', '订单PO-120的合同金额为120万元，服务费为80万元。', [('80万元','SECRET')]),
 ('unknown_label', '附件标签X-PRIVATE-7属于普通归档编号，金额为70万元。', '附件标签X-PRIVATE-8属于普通归档编号，金额为70万元。', []),
 ('mixed_context', '甲方联系人林舟，邮箱lin@example.invalid；内部密码K-77须保密。', '甲方联系人林舟，邮箱lin@example.invalid；合同编号K-77已备案。', [('林舟','PERSON'),('lin@example.invalid','EMAIL'),('K-77','SECRET')]),
 ('unicode_nested', '备注【内层：密钥Ω-9】；外层金额为5.5万元。', '备注【内层：编号Ω-9】；外层金额为5.5万元。', [('密钥Ω-9','SECRET')]),
 ('length_encoding', '地址：虚构市杉桥区映月路8号；账号6222 8800 1234。', '地址：虚构市杉桥区映月路9号；订单号6222 8800 1234。', [('虚构市杉桥区映月路8号','ADDRESS'),('6222 8800 1234','ACCOUNT')]),
]

def row(rid, pair, minimal_pair, mech, variant, text, ents, role):
    entities=[{'text':t,'type':k} for t,k in ents]
    spans(text, entities)
    gs=[]
    for e in entities:
        start=text.find(e['text'])
        gs.append({'start':start,'end':start+len(e['text']),'text':e['text'],'type':e['type']})
    return {'id':rid,'pair_id':pair,'minimal_pair_id':minimal_pair,'variant':variant,'pair_role':role,
            'attack_type':mech,'text':text,'entities':entities,'gold_spans':gs,
            'scoring_scope':[0,len(text)],'source_kind':'synthetic','train_allowed':True,
            'provenance':{'generator':'repair-v6-sample','case':mech,
                          'text_hash':hashlib.sha256(text.encode()).hexdigest()}}

def build(out: Path):
    rows=[]
    for i,(mech,positive,negative,ents) in enumerate(CASES):
        for j,(text,es,role) in enumerate(((positive,ents,'positive'),(negative,[],'negative'))):
            pair=f'RV6-SAMPLE-ATTACK-{i:02d}-{role}'; minimal=f'RV6-SAMPLE-MIN-{i:02d}'
            for variant in ('clean','attack'):
                suffix=' 原文保留。' if variant=='attack' else ''
                rows.append(row(f'{pair}-{variant}',pair,minimal,mech,variant,text+suffix,es,role))
    out.mkdir(parents=True,exist_ok=False); (out/'mlx').mkdir()
    (out/'test.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    (out/'mlx'/'valid.jsonl').write_text(''.join(json.dumps({'messages':messages(r)},ensure_ascii=False)+'\n' for r in rows))
    (out/'manifest.json').write_text(json.dumps({'schema_version':1,'rows':len(rows),'pairs':len(rows)//2,
      'digest':digest(rows),'mechanisms':[x[0] for x in CASES],
      'source':'synthetic only; no historical train/dev/holdout read'},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'BUILT','rows':len(rows),'pairs':len(rows)//2,'output':str(out)}))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); build(ap.parse_args().output)
