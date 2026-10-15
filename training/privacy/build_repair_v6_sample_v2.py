"""Build four-group repair-v6 acceptance sample from structured components."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from common import digest, messages, spans

def make(rid,pair,mini,variant,group,text,entities,role,preserve_text=None,preserve_literals=()):
    es=[{'text':t,'type':k} for t,k in entities]; spans(text,es)
    gs=[]
    for e in es:
        start=text.find(e['text']); assert start>=0
        gs.append({'start':start,'end':start+len(e['text']),'text':e['text'],'type':e['type']})
    r={'id':rid,'pair_id':pair,'minimal_pair_id':mini,'variant':variant,'pair_role':role,
       'attack_type':group,'text':text,'entities':es,'gold_spans':gs,
       'scoring_scope':[0,len(text)],'source_kind':'synthetic','train_allowed':True,
       'preserve_literals':list(preserve_literals),'provenance':{'generator':'repair-v6-sample-v2','group':group,
       'text_hash':hashlib.sha256(text.encode()).hexdigest()}}
    if preserve_text is not None: r['preserve_text']=preserve_text
    return r

def build(out:Path):
    specs=[
      ('floor_public','谈判组内部掌握的最低价格是120万元，年度报价为300万元。','谈判组内部掌握的最低价格是１２０万元，年度报价为300万元。',
       [('120万元','SECRET')],[('１２０万元','SECRET')],'合同服务费为120万元，年度报价为300万元。','合同服务费为１２０万元，年度报价为300万元。',[],('年度报价为300万元',)),
      ('person_billing','联系人魏沐樟，计费标准为12万元/年。','联系人魏 / 沐 / 樟，计费标准为12万元／年。',
       [('魏沐樟','PERSON')],[('魏 / 沐 / 樟','PERSON')],'计费联系人为业务代表，计费标准为12万元/年。','计费联系人为业务代表，计费标准为12万元／年。',[],('计费标准为12万元/年',)),
      ('password_label','签约人林舟，邮箱lin@example.invalid；密码K-77须保密。','签约人林舟，邮箱lin@example.invalid；密码"K-\\u0037\\u0037"须保密。',
       [('林舟','PERSON'),('lin@example.invalid','EMAIL'),('K-77','SECRET')],[('林舟','PERSON'),('lin@example.invalid','EMAIL'),('K-\\u0037\\u0037','SECRET')],
       '签约人林舟，邮箱lin@example.invalid；标签K-77为普通归档编号。','签约人林舟，邮箱lin@example.invalid；标签K-\\u0037\\u0037为普通归档编号。',[('林舟','PERSON'),('lin@example.invalid','EMAIL')],('标签K-77为普通归档编号',)),
      ('account_order','地址为虚构市杉桥区映月路8号，账号622288001234。','地址为虚构市杉桥区映月路8号，账号6222 8800 1234。',
       [('虚构市杉桥区映月路8号','ADDRESS'),('622288001234','ACCOUNT')],[('虚构市杉桥区映月路8号','ADDRESS'),('6222 8800 1234','ACCOUNT')],
       '地址为虚构市杉桥区映月路8号，订单号622288001234。','地址为虚构市杉桥区映月路8号，订单号6222 8800 1234。',[('虚构市杉桥区映月路8号','ADDRESS')],('订单号622288001234',)),
    ]
    rows=[]
    for i,(group,pc,pa,ce,ae,nc,na,ne,pl) in enumerate(specs):
        mini=f'RV6-V2-MIN-{i:02d}'
        for role,(clean,attack,clean_es,attack_es) in enumerate(((pc,pa,ce,ae),(nc,na,ne,ne))):
            pair=f'RV6-V2-PAIR-{i:02d}-{role}'
            for variant,text,es in (('clean',clean,clean_es),('attack',attack,attack_es)):
                preserve_text=text if role==1 and not es else None
                literals=pl if role==1 else tuple(x for x in ('年度报价为300万元','计费标准为12万元/年') if group in {'floor_public','person_billing'})
                if role==0 and variant=='attack':
                    literals=tuple(x.replace('12万元/年','12万元／年') for x in literals)
                if role==1 and variant=='attack':
                    literals=tuple(x.replace('12万元/年','12万元／年').replace('K-77','K-\\u0037\\u0037').replace('622288001234','6222 8800 1234') for x in pl)
                rows.append(make(f'{pair}-{variant}',pair,mini,variant,group,text,es,'positive' if role==0 else 'negative',preserve_text,literals))
    out.mkdir(parents=True,exist_ok=False); (out/'mlx').mkdir()
    (out/'test.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    (out/'mlx'/'valid.jsonl').write_text(''.join(json.dumps({'messages':messages(r)},ensure_ascii=False)+'\n' for r in rows))
    (out/'manifest.json').write_text(json.dumps({'schema_version':2,'rows':len(rows),'pairs':len(rows)//2,'groups':len(specs),'digest':digest(rows),'source':'synthetic structured components only'},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'BUILT','rows':len(rows),'pairs':len(rows)//2,'groups':len(specs),'output':str(out)}))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); build(ap.parse_args().output)
