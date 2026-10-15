import json
import unittest
from urllib.parse import quote
from normalized_view import canonical_view, project
from redact_local import _rule_redact, redact_text, contract_pipeline


class Tokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return messages[-1]['content']
    def encode(self, prompt):
        return list(prompt)


class RepairRuntimeTests(unittest.TestCase):
    def test_unicode_and_encoded_dictionary_preserve_original_amount(self):
        for value in ['孟\u200b映杉','孟\n映杉','孟映杉\u0301',quote('孟映杉'),r'\u5b5f\u6620\u6749','&#23391;&#26144;&#26441;']:
            text='签署人'+value+'，价格３００万元/年。'
            result=_rule_redact(text,[{'text':'孟映杉','type':'PERSON'}])
            self.assertNotIn(value,result['redacted_text'])
            self.assertIn('３００万元/年',result['redacted_text'])
            self.assertTrue(any(text[o['original_start']:o['original_end']]==value for o in result['occurrences']))

    def test_percent_projection_does_not_mask_encoded_neighbor(self):
        original='登记'+''.join(f'%{b:02X}' for b in '孟映杉 300万元'.encode())
        view=canonical_view(original)
        items=project(original,view,[{'text':'孟映杉','type':'PERSON'}])
        self.assertEqual(items,[{'text':quote('孟映杉',safe=''),'type':'PERSON'}])

    def test_alias_and_filename_are_rescued(self):
        text='联系人孟映杉（以下简称“杉代表”）；文件名字段：陶映杉_协议.docx。'
        result=_rule_redact(text,[])
        for literal in ['孟映杉','杉代表','陶映杉']:
            self.assertNotIn(literal,result['redacted_text'])

    def test_model_amount_hallucination_is_filtered_but_secret_retained(self):
        text='退款820元；内部底价为11.5万元。'
        response=json.dumps([{'text':'820元','type':'SECRET'},{'text':'11.5万元','type':'SECRET'}])
        result=redact_text(text,None,Tokenizer(),lambda *a,**kw:response)
        self.assertIn('820元',result['redacted_text'])
        self.assertNotIn('11.5万元',result['redacted_text'])

    def test_same_amount_in_private_and_public_context_blocks(self):
        text='内部底价11.5万元。公开结算标准11.5万元。'
        response=json.dumps([{'text':'11.5万元','type':'SECRET'}])
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS_ENTITY_OCCURRENCE'):
            redact_text(text,None,Tokenizer(),lambda *a,**kw:response)

    def test_ungrounded_model_item_blocks_even_when_rules_work(self):
        with self.assertRaisesRegex(ValueError,'MODEL_ITEMS_UNGROUNDED'):
            redact_text('联系人孟映杉。',None,Tokenizer(),lambda *a,**kw:'[{"text":"不存在的人","type":"PERSON"}]')

    def test_plain_commercial_negative_keeps_meaning(self):
        text='合同编号202809160001，金额每年320万元，未来三年共960万元，税率6%。'
        self.assertEqual(_rule_redact(text,[])['redacted_text'],text)
        self.assertEqual(contract_pipeline.redact(text,[],{},'TEST')[0],text)
        account='合同编号为普通编号，收款账户202809160001。'
        self.assertNotIn('202809160001',contract_pipeline.redact(account,[],{},'TEST')[0])

    def test_transaction_numbers_are_not_projects_but_explicit_project_is(self):
        text = '合同编号HT-2026-A，订单号PO-83044，运单号码YD-2026001，批次号BATCH-2026。项目代号为玄鹭计划。'
        result = _rule_redact(text, [])
        for literal in ['HT-2026-A', 'PO-83044', 'YD-2026001', 'BATCH-2026']:
            self.assertIn(literal, result['redacted_text'])
        self.assertNotIn('玄鹭计划', result['redacted_text'])

    def test_project_prediction_near_transaction_field_is_filtered(self):
        text = '订单编号PO-83044；项目代号玄鹭计划。'
        result = redact_text(text, None, Tokenizer(), lambda *a, **kw: json.dumps([
            {'text': 'PO-83044', 'type': 'PROJECT'},
            {'text': '玄鹭计划', 'type': 'PROJECT'},
        ]))
        self.assertIn('PO-83044', result['redacted_text'])
        self.assertNotIn('玄鹭计划', result['redacted_text'])

    def test_internal_topic_project_cues_are_strictly_scoped(self):
        text = '内部课题：研杉-83040；内部研发代号为星河-07。公开课题标题为合同履约研究。'
        result = _rule_redact(text, [])
        self.assertNotIn('研杉-83040', result['redacted_text'])
        self.assertNotIn('星河-07', result['redacted_text'])
        self.assertIn('合同履约研究', result['redacted_text'])

    def test_split_name_recovery_requires_explicit_name_field(self):
        text = '登记姓名:魏 / 沐 / 樟，以此送达。'
        response = json.dumps([{'text': '魏沐樟', 'type': 'PERSON'}], ensure_ascii=False)
        result = redact_text(text, None, Tokenizer(), lambda *a, **kw: response)
        self.assertNotIn('魏 / 沐 / 樟', result['redacted_text'])

    def test_split_name_recovery_supports_explicit_contact_roles(self):
        for field in ('联系人', '签约人', '授权代表'):
            text = f'{field}：魏 / 沐 / 樟。金额300万元。'
            response = json.dumps([{'text': '魏沐樟', 'type': 'PERSON'}], ensure_ascii=False)
            result = redact_text(text, None, Tokenizer(), lambda *a, **kw: response)
            self.assertNotIn('魏 / 沐 / 樟', result['redacted_text'])
            self.assertIn('300万元', result['redacted_text'])

    def test_split_name_without_name_field_stays_blocked(self):
        response = json.dumps([{'text': '魏沐樟', 'type': 'PERSON'}], ensure_ascii=False)
        with self.assertRaisesRegex(ValueError, 'MODEL_ITEMS_UNGROUNDED'):
            redact_text('备注：魏 / 沐 / 樟。', None, Tokenizer(), lambda *a, **kw: response)

    def test_same_literal_mixed_identifier_and_project_context_blocks(self):
        text = '订单号PO-83044；项目名称：PO-83044。'
        response = json.dumps([{'text': 'PO-83044', 'type': 'PROJECT'}], ensure_ascii=False)
        with self.assertRaisesRegex(ValueError, 'AMBIGUOUS_ENTITY_OCCURRENCE'):
            redact_text(text, None, Tokenizer(), lambda *a, **kw: response)

    def test_minimum_price_cue_masks_first_private_amount_only(self):
        text = '谈判小组内部掌握的最低价格是11.5万元，年度公开报价300万元。'
        result = _rule_redact(text, [])
        self.assertNotIn('11.5万元', result['redacted_text'])
        self.assertIn('300万元', result['redacted_text'])

    def test_public_amount_without_secret_cue_is_preserved(self):
        text = '年度报价300万元，服务费按年支付。'
        self.assertEqual(_rule_redact(text, [])['redacted_text'], text)

    def test_multiple_amounts_keep_public_and_mask_confidential_values(self):
        text = '内部底价11.5万元，公开报价300万元，保密报价88万元。'
        result = _rule_redact(text, [])
        self.assertNotIn('11.5万元', result['redacted_text'])
        self.assertNotIn('88万元', result['redacted_text'])
        self.assertIn('300万元', result['redacted_text'])

    def test_public_market_minimum_price_is_not_secret(self):
        text = '公开市场最低价格为120万元，年度公开报价300万元。'
        self.assertEqual(_rule_redact(text, [])['redacted_text'], text)

    def test_non_public_floor_wins_over_public_substring(self):
        for text in ('不公开的底价为120万元。', '内部保密底价为120万元，公开报价300万元。'):
            result = _rule_redact(text, [])
            self.assertNotIn('120万元', result['redacted_text'])

    def test_public_standard_price_stays_clear_without_confidential_cue(self):
        text = '市场标准最低价格为120万元。'
        self.assertEqual(_rule_redact(text, [])['redacted_text'], text)

    def test_masked_identifier_and_secret_url(self):
        text='证件编号ID-FICT-**，接口https://example.invalid/?key=confidential-token&fee=820元。'
        result=_rule_redact(text,[])
        self.assertNotIn('ID-FICT-**',result['redacted_text'])
        self.assertNotIn('confidential-token',result['redacted_text'])
        self.assertIn('fee=820元',result['redacted_text'])

    def test_alias_cannot_attach_across_unrelated_commercial_sentence(self):
        text='联系人陶映杉。本合同金额简称“总价”，共820万元。'
        result=_rule_redact(text,[])
        self.assertIn('简称“总价”，共820万元',result['redacted_text'])
        self.assertNotIn('陶映杉',result['redacted_text'])
