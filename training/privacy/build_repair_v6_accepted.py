"""Build accepted v6 synthetic contract data; independent validator audits output."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from common import digest, messages

INDUSTRIES = ['procurement','engineering','medical','education','logistics','finance','software','consulting']
COUNTS = {'train': 100, 'dev': 32, 'holdout': 40}

def render(split: str, q: int, role: str, variant: str):
    base = {'train': 1000, 'dev': 3000, 'holdout': 5000}[split] + q
    names = ['周岚','沈砚','唐澜','顾槐','梁弈','许棠','韩序','叶澄','林乔','陈宁','赵妍','李珩','王璇','张弛','刘悦','杨澈','黄蓉','吴桐','郑言','何清','孙宁','马骁','朱瑾','胡安']
    name = names[q % len(names)] + ['宁','华','清','远','安','雅','昕','岳','宏','川','瑾','珩','澜','乔','岚','晖','妍','哲','言','辰','璇','棠','澄','砚'][((q // len(names)) + {'train':0,'dev':8,'holdout':16}[split]) % 24]
    email = f'v6.{base}@example.invalid'; amount = f'{base}万元'; public = f'{base+50}万元'
    address = f'虚构市澄江区云杉路{base}号'; account = f'62170088{base:08d}'
    secret = f'R6-{base}-Q'; project = f'PX-{base}'; order = f'PO-{base}'
    industry = INDUSTRIES[q % 8]; mech = ['private_floor','contact_billing','credential_fee','teacher_contact','address_account','number_context','api_version','project_address'][q % 8]
    attack_method = {'private_floor':'fullwidth_digits','contact_billing':'person_slash','credential_fee':'unicode_escape','teacher_contact':'fullwidth_digits','address_account':'account_grouping','number_context':'fullwidth_digits','api_version':'unicode_escape','project_address':'fullwidth_digits'}[mech]
    pure = role == 'negative' and q % 4 == 0
    if mech == 'private_floor':
        pos = f'采购纪要载明，联系人{name}确认内部最低结算价为{amount}；公告年度报价为{public}。'; neg = f'采购公告载明，年度服务报价为{public}，交付周期为12个月。'
        ents = [(name,'PERSON'),(amount,'SECRET')]; preserve = [f'公告年度报价为{public}。']
    elif mech == 'contact_billing':
        pos = f'工程变更单由{name}签字，邮箱{email}接收现场通知；协调服务费按每月4.8万元结算。'; neg = f'工程变更单{base}载明，协调服务费按公开费率每月4.8万元结算。'
        ents = [(name,'PERSON'),(email,'EMAIL')]; preserve = ['协调服务费按公开费率每月4.8万元结算。' if role == 'negative' else '协调服务费按每月4.8万元结算。']
    elif mech == 'credential_fee':
        pos = f'医疗授权记录由{name}保管，凭据{secret}通过{email}传递；患者标准费用为6800元。'; neg = f'医疗服务说明{base}载明患者标准费用为6800元，预约时段为上午。'
        ents = [(name,'PERSON'),(secret,'SECRET'),(email,'EMAIL')]; preserve = ['患者标准费用为6800元。']
    elif mech == 'teacher_contact':
        pos = f'培训合同由{name}负责，资料发送至{email}；课程《合同法基础》公开学费为3200元。'; neg = f'公开课程目录{base}列明《合同法基础》报名费为3200元，开课日期为9月。'
        ents = [(name,'PERSON'),(email,'EMAIL')]; preserve = ['报名费为3200元，开课日期为9月' if role == 'negative' else '课程《合同法基础》公开学费为3200元。']
    elif mech == 'address_account':
        pos = f'物流委托书指定{name}将货物送至{address}，运费结算账户为{account}。'; neg = f'物流公告载明普通配送费为8600元，服务时间为工作日。'
        ents = [(name,'PERSON'),(address,'ADDRESS'),(account,'ACCOUNT')]; preserve = []
    elif mech == 'number_context':
        pos = f'财务复核表显示项目{project}公开预算为{public}；谈判记录内部限价为{amount}，由{name}复核。'; neg = f'财务复核表显示订单{order}公开金额为{public}；服务费为{amount}。'
        ents = [(project,'PROJECT'),(amount,'SECRET'),(name,'PERSON')]; preserve = [f'公开金额为{public}' if role == 'negative' else f'公开预算为{public}']
    elif mech == 'api_version':
        pos = f'软件交付由{name}验收，生产密钥{secret}通过{email}传递，客户端版本为v3.4.1。'; neg = f'软件交付清单列明普通文档编号SDK-{base}，客户端版本为v3.4.1。'
        ents = [(name,'PERSON'),(secret,'SECRET'),(email,'EMAIL')]; preserve = ['客户端版本为v3.4.1。']
    else:
        pos = f'咨询合同指定{name}负责项目“咨询项目{base}”，资料寄送至{address}；合同总价为45万元。'; neg = f'咨询宣传页列示项目“公开咨询{base}”服务总价为45万元。'
        ents = [(name,'PERSON'),(f'咨询项目{base}','PROJECT'),(address,'ADDRESS')]; preserve = ['服务总价为45万元' if role == 'negative' else '合同总价为45万元']
    text = neg if role == 'negative' else pos
    if pure:
        pure_texts = {'train':'服务公告载明：标准服务时间为工作日，公开费率按合同附件执行。','dev':'服务协议约定：工作日提供标准支持，费用依附件价目表结算。','holdout':'服务条款说明：标准支持安排在工作日，收费依双方确认的价目表执行。'}
        text = pure_texts[split]; ents = []; preserve = [text]
    if role == 'negative' and mech == 'number_context':
        ents = [(v,t) for v,t in ents if t != 'SECRET']
    if not pure and split == 'train': text = '签约附件载明：' + text
    elif not pure and split == 'dev': text = '履约记录记载：' + text
    elif not pure: text = '双方确认书载明：' + text
    if variant == 'attack':
        trans = str.maketrans('0123456789', '０１２３４５６７８９')
        text = text.translate(trans).replace('。', '．')
        ents = [(v.translate(trans), t) for v,t in ents]
        preserve = [v.translate(trans).replace('。', '．') for v in preserve]
        if mech == 'contact_billing' and ents:
            # lossless slash insertion is meaningful only for PERSON.
            ents = [(' / '.join(v), t) if t == 'PERSON' else (v, t) for v,t in ents]
            text = text.replace(name.translate(trans), ' / '.join(name.translate(trans)))
        if mech == 'api_version':
            encoded = lambda v: ''.join('\\u%04x' % ord(c) for c in v)
            text = text.replace(secret.translate(trans), encoded(secret.translate(trans)))
            ents = [(encoded(v), t) if t == 'SECRET' else (v, t) for v,t in ents]
        if mech == 'address_account':
            grouped = ' '.join(account.translate(trans)[i:i+4] for i in range(0, len(account), 4))
            text = text.replace(account.translate(trans), grouped)
            ents = [(grouped, t) if t == 'ACCOUNT' else (v, t) for v,t in ents]
    return text, ents, preserve, industry, mech

def make(split, q, role, variant):
    text, pairs, preserve, industry, mech = render(split,q,role,variant)
    attack_method = {'private_floor':'fullwidth_digits','contact_billing':'person_slash','credential_fee':'unicode_escape','teacher_contact':'fullwidth_digits','address_account':'account_grouping','number_context':'fullwidth_digits','api_version':'unicode_escape','project_address':'fullwidth_digits'}[mech]
    if role == 'positive' and any(v not in text for v,t in pairs):
        raise ValueError(f'POSITIVE_ENTITY_NOT_RENDERED:{split}:{q}:{variant}')
    pairs = [(v,t) for v,t in pairs if v in text]
    preserve = [value[:-1] if value.endswith(('。','．')) and value[:-1] in text else value for value in preserve]
    if any(value not in text for value in preserve):
        raise ValueError(f'PRESERVE_NOT_RENDERED:{split}:{q}:{role}:{variant}')
    entities = [{'text':v,'type':t} for v,t in pairs]
    spans = [{'start':text.find(v),'end':text.find(v)+len(v),'text':v,'type':t} for v,t in pairs]
    pair = f'R6-P{q:03d}-{role[0]}'; mini=f'R6-M{q:03d}'; tid=f'r6-{split[0]}-t{q%8:02d}'
    row = {'id':f'{pair}-{role[0]}-{variant}','pair_id':pair,'minimal_pair_id':mini,'variant':variant,'pair_role':role,'attack_type':mech,'attack_methods':[attack_method] if variant=='attack' else [],'industry':industry,'template_id':tid,'text':text,'entities':entities,'gold_spans':spans,'scoring_scope':[0,len(text)],'preserve_literals':preserve,'invariant_components':['PERSON','EMAIL','ADDRESS'] if role=='positive' else [],'source_kind':'synthetic','train_allowed':split!='holdout','provenance':{'generator':'repair-v6-reviewed','text_hash':hashlib.sha256(text.encode()).hexdigest()}}
    if not entities: row['preserve_text'] = text
    return row

def build(out: Path):
    if out.exists(): raise FileExistsError(out)
    out.mkdir(parents=True); (out/'mlx').mkdir(); allrows={}
    for split,count in COUNTS.items():
        rows=[make(split,q,role,var) for q in range(count) for role in ('positive','negative') for var in ('clean','attack')]
        allrows[split]=rows; (out/f'{split}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
        if split != 'holdout': (out/'mlx'/('train.jsonl' if split=='train' else 'valid.jsonl')).write_text(''.join(json.dumps({'messages':messages(r)},ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'schema_version':3,'rows':{k:len(v) for k,v in allrows.items()},'templates':24,'source':'synthetic contract context','holdout_sha256':hashlib.sha256((out/'holdout.jsonl').read_bytes()).hexdigest(),'digests':{k:digest(v) for k,v in allrows.items()}},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); build(p.parse_args().output)
