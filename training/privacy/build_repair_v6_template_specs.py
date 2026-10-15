"""Emit 24 reviewed template definitions; no training/holdout rows are generated."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

INDUSTRIES=['procurement','engineering','medical','education','logistics','finance','software','consulting']
MECHANISMS=['floor_public','slash_person','password_label','account_order','multi_secret','literal_conflict','mixed_unknown','length_nested']
SPECS={
'floor_public':['采购谈判纪要记载：内部最低价为<PRIVATE_AMOUNT>；公告年度报价为<PUBLIC_AMOUNT>。','工程变更审批中，谈判组内部掌握的最低价格是<PRIVATE_AMOUNT>，对外年度报价为<PUBLIC_AMOUNT>。','医疗服务比价表：内部底价<PRIVATE_AMOUNT>，患者可见的标准年费为<PUBLIC_AMOUNT>。'],
'slash_person':['项目负责人为<PERSON>，本年度计费标准为<BILLING_AMOUNT>/<UNIT_YEAR>。','请<PERSON>在交付单签字；费用按<BILLING_AMOUNT>/<UNIT_YEAR>结算。','联系人栏填写<PERSON>，其服务单价为<BILLING_AMOUNT>/<UNIT_YEAR>。'],
'password_label':['账号由<PERSON>（<EMAIL>）维护，机密口令<PASSWORD>仅限值班人员使用。','值守交接单：<PERSON>、<EMAIL>；认证密钥<PASSWORD>不得写入普通标签。','服务台记录<PERSON>/<EMAIL>，其中<PASSWORD>属于保密凭据，标签字段保持普通。'],
'account_order':['收货地址为<ADDRESS>，结算账户<ACCOUNT>已核验。','向<ADDRESS>配送；本次订单号<ORDER_ID>，付款账户<ACCOUNT>另行留存。','客户资料含<ADDRESS>及账户<ACCOUNT>，关联项目号<PROJECT_ID>。'],
'multi_secret':['报价单同时列出内部底价<PRIVATE_AMOUNT_A>、公开报价<PUBLIC_AMOUNT>及内部封顶价<PRIVATE_AMOUNT_B>。','委员会记录：可公开金额<PUBLIC_AMOUNT>夹在两项谈判底价<PRIVATE_AMOUNT_A>与<PRIVATE_AMOUNT_B>之间。','年度预算页展示<PUBLIC_AMOUNT>；保密栏另列最低价<PRIVATE_AMOUNT_A>和最高授权价<PRIVATE_AMOUNT_B>。'],
'literal_conflict':['项目号<PROJECT_ID>对应预算<PUBLIC_AMOUNT>，但谈判底价为<PRIVATE_AMOUNT>。','订单号<ORDER_ID>与项目编号<PROJECT_ID>共享尾号；合同金额<PUBLIC_AMOUNT>，内部底价<PRIVATE_AMOUNT>。','同一数字出现在订单<ORDER_ID>和项目<PROJECT_ID>；仅“内部报价<PRIVATE_AMOUNT>”属于敏感字段。'],
'mixed_unknown':['普通标签<LABEL>、联系人<PERSON>、邮箱<EMAIL>及备注“金额<PUBLIC_AMOUNT>”。','Field <LABEL> is ordinary; <PERSON> (<EMAIL>) handles the public fee <PUBLIC_AMOUNT>.','系统字段<LABEL>不代表敏感类型；通知联系人<PERSON>/<EMAIL>，公开金额<PUBLIC_AMOUNT>。'],
'length_nested':['附件 JSON：{"meta":{"owner":"<PERSON>"},"secret":"<PASSWORD>"}；字节长度<LENGTH>。','嵌套交付对象含 code=<PASSWORD> 与 note=<LABEL>，超长备注<LONG_TEXT>位于边界。','多语言字段：{"zh":"<PASSWORD>","en":"<PASSWORD_EN>"}；长度阈值前后分别为<LENGTH_A>/<LENGTH_B>。'],
}
ENTITY_POOL={'PERSON':['张伟','李娜','王磊','陈晨','赵敏','刘洋'],'EMAIL':['liaison@example.invalid'],'PASSWORD':['K-7719'],'PRIVATE_AMOUNT':['120万元'],'PRIVATE_AMOUNT_A':['80万元'],'PRIVATE_AMOUNT_B':['150万元'],'PUBLIC_AMOUNT':['300万元'],'BILLING_AMOUNT':['12万元'],'UNIT_YEAR':['年'],'ACCOUNT':['622288001234'],'ADDRESS':['上海市静安区虚构路8号'],'PROJECT_ID':['PX-120'],'ORDER_ID':['PO-120'],'LABEL':['ARCHIVE-7'],'LENGTH':['128字节'],'LENGTH_A':['127字节'],'LENGTH_B':['129字节'],'LONG_TEXT':['边界文本'],'PASSWORD_EN':['K-7719']}
ENCODINGS={'PERSON':['identity','slash_components'],'PRIVATE_AMOUNT':['identity','fullwidth_digits'],'PRIVATE_AMOUNT_A':['identity','fullwidth_digits'],'PRIVATE_AMOUNT_B':['identity','fullwidth_digits'],'PASSWORD':['identity','json_escape'],'PASSWORD_EN':['identity','json_escape'],'ACCOUNT':['identity','group_4_digits']}

def decode_encode_assertions():
    person='张伟'; slash=' / '.join(person); assert ''.join(slash.split(' / '))==person
    amount='120万元'; fw=amount.translate(str.maketrans('0123456789','０１２３４５６７８９')); assert fw.translate(str.maketrans('０１２３４５６７８９','0123456789'))==amount
    pw='K-7719'; esc='K-\\u0037\\u0037\\u0031\\u0039'; assert ''.join(chr(int(x,16)) for x in esc.split('\\u')[1:])=='7719'
    acc='622288001234'; grouped=' '.join(acc[i:i+4] for i in range(0,len(acc),4)); assert grouped.replace(' ','')==acc

def build(out:Path):
    decode_encode_assertions(); rows=[]
    for split,idx in [('train',0),('dev',1),('holdout',2)]:
        for i,m in enumerate(MECHANISMS):
            text=SPECS[m][idx]; tid=f'v6-{split}-template-{i:02d}'
            rows.append({'template_id':tid,'split':split,'industry':INDUSTRIES[i],'mechanism':m,'text_template':text,'placeholder_entities':sorted(set(x.strip('<>') for x in re.findall(r'<[^>]+>',text))),'gold_rule':'Render components, then derive common.spans; never hand-write offsets.','encodings':ENCODINGS,'source_kind':'synthetic','template_hash':hashlib.sha256(text.encode()).hexdigest()})
    out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({'schema_version':1,'template_count':len(rows),'templates':rows,'entity_pool':ENTITY_POOL,'encoding_inverse_assertions':'passed','split_policy':'8 mechanisms and 8 industries per split; template_id disjoint'},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'BUILT','templates':len(rows),'output':str(out)}))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); build(ap.parse_args().output)
