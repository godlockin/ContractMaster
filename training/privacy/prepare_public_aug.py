"""Synthetic multilingual/public-style augmentation; no external validation text copied."""
import argparse, json, random
from pathlib import Path
from common import rows, messages, spans, digest, dump


def build(output: Path, count: int = 1800, public_path: Path = Path('artifacts/privacy/data/openpii-train/train.jsonl')) -> None:
    base = rows(Path('artifacts/privacy/data/v3/train.jsonl')) + rows(Path('artifacts/privacy/data/v6/augmentation.jsonl')) + rows(public_path)
    dev = rows(Path('artifacts/privacy/data/v3/dev.jsonl'))
    surnames = ['王','李','张','陈','刘','赵','杨','黄','周','吴']
    given = ['明远','晓宁','嘉怡','子涵','文博','思雨','浩然','清和']
    templates = [
        '请将通知发送给{person}，邮箱为{email}。',
        '登记地址：{address}；联系人：{person}。',
        '证件代码{ident}须与账户{account}一并核验。',
        '紧急电话{phone}，备用邮箱{email}。',
        '供应商{org}位于{address}，授权人员为{person}。',
        '护照或证件编号：{ident}；联系电话：{phone}。',
        '付款账户{account}，普通金额{amount}元。',
        '邮件抄送{email}，项目名称为{project}。',
        '公开会议地点在{address}，日期为2028年5月6日。',
    ]
    records = []
    for i in range(count):
        person = surnames[i % len(surnames)] + given[(i // len(surnames)) % len(given)]
        if i % 7 == 0: person = 'Mr. ' + person
        city = ['上海市','杭州市','深圳市','示例市'][i % 4]
        address = f'{city}{["青浦区","西湖区","南山区","星河区"][i%4]}云锦路{i+1200}号'
        email = f'{"联系" if i%3 else "legal"}{i}@sample.invalid'
        phone = f'+86 {139 + i % 10:03d} {i%10000:04d} {1000+i%9000:04d}'
        ident = f'{["NLW","DX","HP","TVC"][i%4]}{i:07d}'
        account = f'{6222000000000000000 + i}'
        org = f'{["澜庭","嵩禾","栖原","青岚"][i%4]}{i}服务有限公司'
        project = f'内部项目-{i:04d}'
        amount = 100 + i % 900
        template = templates[i % len(templates)]
        text = template.format(person=person,email=email,address=address,phone=phone,ident=ident,account=account,org=org,project=project,amount=amount)
        entities=[]
        for key, value, kind in [('person',person,'PERSON'),('email',email,'EMAIL'),('address',address,'ADDRESS'),('phone',phone,'PHONE'),('ident',ident,'ID'),('account',account,'ACCOUNT'),('org',org,'ORG'),('project',project,'PROJECT')]:
            if '{'+key+'}' in template: entities.append({'text':value,'type':kind})
        spans(text, entities)
        records.append({'id':f'public-augmentation-{i:05d}','family':f'public-augmentation-{i%len(templates)}','text':text,'entities':entities,'source':'original-public-style-fiction'})
    combined = base + records
    random.Random(20260918).shuffle(combined)
    output.mkdir(parents=True, exist_ok=False); (output/'mlx').mkdir()
    (output/'mlx'/'train.jsonl').write_text(''.join(json.dumps({'messages':messages(r)},ensure_ascii=False)+'\n' for r in combined),encoding='utf-8')
    (output/'mlx'/'valid.jsonl').write_text(''.join(json.dumps({'messages':messages(r)},ensure_ascii=False)+'\n' for r in dev),encoding='utf-8')
    dump(output/'manifest.json', {'recipe':'public-style-multilingual-synthetic-v1','base_rows':len(base),'augmentation_rows':len(records),'training_rows':len(combined),'validation_digest':digest(dev),'test_loaded':False})
    print(json.dumps({'status':'PUBLIC_STYLE_AUGMENTED','training_rows':len(combined)}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--count',type=int,default=1800); parser.add_argument('--public',type=Path,default=Path('artifacts/privacy/data/openpii-train/train.jsonl')); args=parser.parse_args(); build(args.output,args.count,args.public)
