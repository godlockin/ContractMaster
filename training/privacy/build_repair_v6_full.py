"""Generate repair-v6 train/dev/fresh-holdout quartets from synthetic components."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from common import digest, messages, spans

INDUSTRIES=['procurement','engineering','medical','education','logistics','finance','software','consulting']
MECHANISMS=['floor_public','slash_person','password_label','account_order','multi_secret','literal_conflict','mixed_unknown','length_nested']
COUNTS={'train':100,'dev':32,'holdout':40}

def data_for(m,i):
    n=100+i; person=f'顾问{chr(0x4e00+i%8)}{chr(0x821f+i%7)}'; email=f'v6-{i}@example.invalid'
    if m=='floor_public': return (f'谈判组内部掌握的最低价格是{n}万元，年度报价为300万元。',f'谈判组内部掌握的最低价格是{n}．０万元，年度报价为300万元。',[(''+str(n)+'万元','SECRET')],[(''+str(n)+'．０万元','SECRET')],f'合同服务费为{n}万元，年度报价为300万元。',f'合同服务费为{n}万元，年度报价为300万元。',[],['年度报价为300万元'])
    if m=='slash_person': return (f'联系人{person}负责签署，计费标准为12万元/年。',f'联系人{" / ".join(person)}负责签署，计费标准为12万元／年。',[(person,'PERSON')],[(' / '.join(person),'PERSON')],'联系人为业务代表，计费标准为12万元/年。','联系人为业务代表，计费标准为12万元／年。',[],['计费标准为12万元/年'])
    if m=='password_label': return (f'签约人{person}，邮箱{email}；密码K-{n}须保密。',f'签约人{person}，邮箱{email}；密码"K-\\u003{n%10}\\u003{n%10}"须保密。',[(person,'PERSON'),(email,'EMAIL'),(f'K-{n}','SECRET')],[(person,'PERSON'),(email,'EMAIL'),(f'K-\\u003{n%10}\\u003{n%10}','SECRET')],f'签约人{person}，邮箱{email}；标签K-{n}为普通归档编号。',f'签约人{person}，邮箱{email}；标签K-\\u003{n%10}\\u003{n%10}为普通归档编号。',[(person,'PERSON'),(email,'EMAIL')],[f'标签K-{n}为普通归档编号'])
    if m=='account_order': return (f'地址为虚构市杉桥区映月路{n}号，账号622288{n:06d}。',f'地址为虚构市杉桥区映月路{n}号，账号6222 88{n:02d} {n:04d}。',[(f'虚构市杉桥区映月路{n}号','ADDRESS'),(f'622288{n:06d}','ACCOUNT')],[(f'虚构市杉桥区映月路{n}号','ADDRESS'),(f'6222 88{n:02d} {n:04d}','ACCOUNT')],f'地址为虚构市杉桥区映月路{n}号，订单号622288{n:06d}。',f'地址为虚构市杉桥区映月路{n}号，订单号6222 88{n:02d} {n:04d}。',[(f'虚构市杉桥区映月路{n}号','ADDRESS')],[f'订单号622288{n:06d}'])
    if m=='multi_secret': return (f'内部底价{n}万元，公开报价300万元，内部封顶价{n+10}万元。',f'内部底价{n}万元，公开报价300万元，内部封顶价{n+10}．０万元。',[(f'内部底价{n}万元','SECRET'),(f'内部封顶价{n+10}万元','SECRET')],[(f'内部底价{n}万元','SECRET'),(f'内部封顶价{n+10}．０万元','SECRET')],f'服务费{n}万元，公开报价300万元，年度上限{n+10}万元。',f'服务费{n}万元，公开报价300万元，年度上限{n+10}．０万元。',[],['公开报价300万元'])
    if m=='literal_conflict': return (f'项目PX-{n}预算为120万元，内部底价为80万元。',f'项目PX-{n}预算为１２０万元，内部底价为80万元。',[('PX-'+str(n),'PROJECT'),('120万元','SECRET'),('80万元','SECRET')],[('PX-'+str(n),'PROJECT'),('１２０万元','SECRET'),('80万元','SECRET')],f'订单PO-{n}金额为120万元，服务费为80万元。',f'订单PO-{n}金额为１２０万元，服务费为80万元。',[],[f'订单PO-{n}金额为120万元，服务费为80万元。'])
    if m=='mixed_unknown': return (f'普通标签X-{n}，联系人{person}，备注金额70万元。',f'普通标签X-{n}，联系人{" / ".join(person)}，备注金额７０万元。',[(person,'PERSON')],[(" / ".join(person),'PERSON')],f'普通标签X-{n}，联系人为业务代表，备注金额70万元。',f'普通标签X-{n}，联系人为业务代表，备注金额７０万元。',[],[f'普通标签X-{n}，联系人为业务代表，备注金额70万元。'])
    return (f'嵌套字段{{"secret":"K-{n}","note":"普通"}}，附件长度128字节。',f'嵌套字段{{"secret":"K-\\u003{n%10}","note":"普通"}}，附件长度１２８字节。',[(f'K-{n}','SECRET')],[(f'K-\\u003{n%10}','SECRET')],f'嵌套字段{{"code":"K-{n}","note":"普通"}}，附件长度128字节。',f'嵌套字段{{"code":"K-\\u003{n%10}","note":"普通"}}，附件长度１２８字节。',[],[f'嵌套字段{{"code":"K-{n}","note":"普通"}}，附件长度128字节。'])

def row(rid,pair,mini,var,role,mech,template,text,ents,lits):
    es=[{'text':t,'type':k} for t,k in ents]; spans(text,es); gs=[]
    for e in es:
        s=text.find(e['text']); gs.append({'start':s,'end':s+len(e['text']),'text':e['text'],'type':e['type']})
    out={'id':rid,'pair_id':pair,'minimal_pair_id':mini,'variant':var,'pair_role':role,'attack_type':mech,'industry':INDUSTRIES[template%8],
         'template_id':f'v6-template-{template:02d}','text':text,'entities':es,'gold_spans':gs,'scoring_scope':[0,len(text)],'preserve_literals':lits,
         'source_kind':'synthetic','train_allowed':True,'provenance':{'generator':'repair-v6-full','template_hash':hashlib.sha256(str(template).encode()).hexdigest(),'text_hash':hashlib.sha256(text.encode()).hexdigest()}}
    if role=='negative' and not es: out['preserve_text']=text
    return out

def attack_literals(lits,text):
    out=[]
    for x in lits:
        y=x.replace('/','／').replace('622288','6222 88')
        if x.startswith('订单号'):
            md=re.search(r'订单号622288(\d{6})',x)
            if md: y=f'订单号6222 88{int(md.group(1)):02d} {int(md.group(1)):04d}'
        if y not in text and 'K-' in y:
            y=re.sub(r'(K-)(\d+)',lambda m:m.group(1)+''.join('\\u003'+d for d in m.group(2)),y)
        if y not in text:
            y=y.replace('120万元','１２０万元').replace('70万元','７０万元').replace('128字节','１２８字节')
        if y not in text and y not in text:
            y=''.join(chr(ord(c)+0xfee0) if '0'<=c<='9' else c for c in y)
        out.append(y)
    return out

def build(out):
    out.mkdir(parents=True,exist_ok=False); allrows={}
    for split,count in COUNTS.items():
        rows=[]; template_base={'train':0,'dev':8,'holdout':16}[split]
        for q in range(count):
            mech=MECHANISMS[q%8]; t=template_base+(q%8); pc,pa,pe,pae,nc,na,ne,lits=data_for(mech,q+(0 if split=='train' else 1000 if split=='dev' else 2000))
            mini=f'RV6-{split}-MIN-{q:03d}'
            for role,(c,a,ce,ae) in enumerate(((pc,pa,pe,pae),(nc,na,ne,ne))):
                pair=f'RV6-{split}-PAIR-{q:03d}-{role}'
                for var,txt,es in (('clean',c,ce),('attack',a,ae)):
                    txt=f'样本{split}-{q}-'+txt
                    base_lits=lits if role==1 else ([x for x in ('年度报价为300万元','计费标准为12万元/年') if x in c])
                    ll=attack_literals(base_lits,txt) if var=='attack' else base_lits
                    ll=[x for x in ll if x in txt]
                    rows.append(row(f'{pair}-{var}',pair,mini,var,'positive' if role==0 else 'negative',mech,t,txt,es,ll))
        allrows[split]=rows; (out/f'{split}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
        if split!='holdout':
            (out/'mlx').mkdir(exist_ok=True); (out/'mlx'/f'{"train" if split=="train" else "valid"}.jsonl').write_text(''.join(json.dumps({'messages':messages(r)},ensure_ascii=False)+'\n' for r in rows))
    (out/'manifest.json').write_text(json.dumps({'schema_version':2,'rows':{k:len(v) for k,v in allrows.items()},'quartets':COUNTS,'mechanisms':MECHANISMS,'industries':INDUSTRIES,'template_split':{'train':list(range(8)),'dev':list(range(8,16)),'holdout':list(range(16,24))},'digests':{k:digest(v) for k,v in allrows.items()},'source':'synthetic structured components only','holdout_policy':'fresh frozen;正文不得提供给训练 agent'},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'BUILT','rows':{k:len(v) for k,v in allrows.items()},'quartets':COUNTS}))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); build(ap.parse_args().output)
