"""Freeze a fresh blind set after all development-driven changes.

Only newly generated fictitious text is used. This set must not be loaded by
training or used to tune guardrails before its first candidate evaluation.
"""
import argparse, json, random
from pathlib import Path
from common import spans, digest, dump


def build(output: Path, count: int = 80, offset: int = 0) -> None:
    if count <= 0:
        raise ValueError('INVALID_BLIND_COUNT')
    templates = [
        ('收件主体记载为{org}，授权签署人是{person}，送达地址写作{address}。', [('org','ORG'),('person','PERSON'),('address','ADDRESS')]),
        ('付款资料：账户{account}；核验凭证{ident}；专用邮箱{email}。', [('account','ACCOUNT'),('ident','ID'),('email','EMAIL')]),
        ('内部方案“{project}”仅供谈判组使用，秘密底价为{secret}，公开报价另计。', [('project','PROJECT'),('secret','SECRET')]),
        ('技术交付单列明：{formula}。普通服务费为300万元/年。', [('formula','SECRET')]),
        ('请通过{email}联系{person}，电话{phone}；合同期限三年。', [('email','EMAIL'),('person','PERSON'),('phone','PHONE')]),
        ('公开法律条文和付款日期不属于敏感信息，年度金额300万元。', []),
    ]
    surnames='梁郭马罗宋唐'; given='景行知夏清和予安'
    records=[]
    for i in range(count):
        n = i + offset
        org=f'远汀{n}供应链有限公司'; person=surnames[n%len(surnames)]+given[(n//len(surnames))%len(given)]
        address=f'示例省远汀市澄明区云栖路{n+410}号'; account=f'6217000000000{n:06d}'
        ident=f'ZB{n:08d}X'; email=f'case{n}@blind.invalid'; phone=f'1{(3+n%7)}900{n:07d}'[:11]
        project=f'镜浦专项-{n:03d}'; secret=f'{20+n%70}.{n%10}万元'; formula=f'组分甲{n%9+2}份与组分乙{n%7+1}份'
        values=locals(); template, fields=templates[n%len(templates)]; text=template.format(**values)
        entities=[{'text':values[key],'type':kind} for key,kind in fields]; spans(text,entities)
        records.append({'id':f'blind-{n:04d}','family':f'blind-{n%len(templates)}','text':text,'entities':entities,'source':'fresh-original-fiction-blind','train_allowed':False})
    random.Random(20260920 + offset).shuffle(records)
    output.mkdir(parents=True,exist_ok=False)
    (output/'test.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    dump(output/'manifest.json',{'rows':len(records),'digest':digest(records),'train_allowed':False,'created_after':'v4-step160-and-guardrails','independent_of_prior_text':True})
    print(json.dumps({'status':'BLIND_SET_FROZEN','rows':len(records),'digest':digest(records)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--count',type=int,default=80); parser.add_argument('--offset',type=int,default=0); args=parser.parse_args(); build(args.output,args.count,args.offset)
