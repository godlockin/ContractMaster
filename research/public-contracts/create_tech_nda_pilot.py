"""Materialize this run's independent AI pilot notes with exact source offsets.

Not an automatic legal reviewer; findings below were authored after reading stated pages.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT=Path(__file__).resolve().parent

def evidence(text,begin,end=None):
    start=text.index(begin)
    finish=start+len(begin) if end is None else text.index(end,start)+len(end)
    quote=text[start:finish]
    page=int(list(re.finditer(r'\[PAGE (\d+)\]',text[:start]))[-1].group(1))
    return {'quote':quote,'start':start,'end':finish,'page':page}

def finding(ident,severity,perspective,risk,impact,suggestion,quotes,questions):
    return dict(id=ident,severity=severity,perspective=perspective,risk=risk,impact=impact,suggestion=suggestion,evidence=quotes,basis={'status':'unverified','type':'contract_text_and_conditional_commercial_analysis','note':'本轮未检索核验现行适用法律/司法解释/外国法；文本观察不等于违法或无效判断。'},questions=questions)

def main():
    t=(ROOT/'sanitized/P05.txt').read_text(); n=(ROOT/'sanitized/P07.txt').read_text()
    f=[]
    f.append(finding('P05-T01','medium','法务/业务范围','2001年汇编需先选模板及核验适用时点','若将汇编直接当一份当前交易合同，可能混合委托与合作等不同交易，或把历史法律表述当作当前规则。不能据旧引用单独认定合同无效。','先分离所需模板并确认交易类型、签署时间、立场与法域，再核验当前法源；保留其他模板为参考，不建立跨模板矛盾。',[evidence(t,'国科发政字［2001］244 号'),evidence(t,'附件 1：技术开发(委托)合同','附件 4：技术转让(专利权)合同'),evidence(t,'附件 5：技术转让(专利实施许可)合同','附件 8：技术服务合同')],['拟评估的是委托开发、合作开发还是其他交易？签署/履行时间是什么？']))
    f.append(finding('P05-T02','high','业务/财务/技术履约','委托开发需把技术目标、付款、交付和验收绑成可执行里程碑','模板分别提供栏目，但未预设联动机制。若签署时仍缺客观验收标准及付款触发，双方可能对完成程度、尾款和整改产生争议；空白模板本身不是违法。','形成里程碑附件，逐项列明输入依赖、交付物、验收测例/期限、整改复验、付款触发和逾期责任；正文确认附件优先关系。',[evidence(t,'第一条  本合同研究开发项目的要求如下：'),evidence(t,'第五条  甲方应按以下方式支付研究开发经费和报酬：'),evidence(t,'第十二条  乙方应当按以下方式向甲方交付研究开发成果：','第十四条')],['付款是否先于验收？验收失败时如何整改和处理已付款？源代码、文档、环境能否独立运行？']))
    f.append(finding('P05-T03','high','法务/争议/业务变更','书面协商一致与特定情形沉默视为同意需收紧边界','第七条同时规定书面一致与逾期不答视为同意。若例外范围和送达证据宽泛，可能在未明确确认时改变费用、范围或工期；该例外并非当然自相矛盾。','限定可适用沉默机制的具体非重大事项；价款、IP、范围、工期和责任变更须授权代表明确书面同意；明确到达、回复期限及提醒。',[evidence(t,'第七条  本合同的变更必须由双方协商一致','视为同意：')],['哪些变更可以沉默同意？通知发给项目联系人是否具有合同变更授权？']))
    f.append(finding('P05-T04','high','技术/信息安全/供应链','分包例外与技术资料保密需要联动','第八条允许约定未经同意的研发转交例外；第十一条保密栏目未自动把该例外中的第三方纳入约束。涉及代码、数据或核心技术时，单纯列保密期限不够支撑外包执行。','列明允许转交范围、获准第三方、再分包条件及原受托方责任；关联保密/访问控制/数据用途、存储位置、事件通报、返还删除及验收要求。仅在实际涉及相应数据时适用专项控制。',[evidence(t,'第八条  未经甲方同意','乙方可以转让研究开发工作的具体内容包括：'),evidence(t,'第十一条  双方确定因履行本合同应遵守的保密义务如下：')],['是否会外包或使用云/AI工具？谁可以接触甲方材料？是否涉及个人信息、重要数据或跨境访问？']))
    f.append(finding('P05-T05','high','知识产权/技术/商业','专利和技术秘密选项未直接解决所有交付及持续使用权','第十五条给出专利/技术秘密及特别约定；第十六条限制交付前对第三方转让，第十九/二十一条另涉培训及改进。软件项目若只勾选其中一个选项，仍需确定软件著作权、背景技术和第三方组件等具体权利，不能把后续改进或交付后转让一概视为被禁止。','在特别约定中分清背景/项目/后续成果、软件和文档权利、第三方及开源许可、部署修改和再许可权限、源码与构建材料交付；协调第十四条侵权处置与第十九/二十一条。',[evidence(t,'第十五条  双方确定','2．按技术秘密方式处理。'),evidence(t,'第十六条  乙方不得','果转让给第三人。'),evidence(t,'第二十一条  双方确定','第二十二条')],['项目是否包含软件？甲方需要所有权还是充分使用许可？交付后能否向竞争对手许可同成果？']))
    f.append(finding('P05-T06','high','财务/技术风险/争议解决','合理研发失败与解除后的费用及成果处置需明确','第九条规定合理技术失败、损失分配和认定；第二十三条允许技术风险导致的不必要/不可能履行解除。若采用模板但未写清证明、已付经费、在研成果及退出交接，解除争议会同时影响现金流和研发继续。','区分无过错技术失败与延期/违约；约定独立评估、通知减损、阶段结算/退款、在研代码和资料移交、后续使用权及保密存续。',[evidence(t,'第九条  在本合同履行中','第十条'),evidence(t,'第二十三条  双方确定','第二十四条')],['技术风险由谁认定？失败时剩余经费如何返还？谁继续使用阶段成果及接管项目？']))
    g=[]
    g.append(finding('P07-N01','high','业务/保密期限','保密保护从生效日计算，并非每次披露或终止后重新起算','第1条固定Effective Date后三年，第12条一年合同期并引用第1条。对临近到期披露的信息，剩余保护期更短；不能误读为终止后再保护三年。','按双方业务保密生命周期明确起算点；如需按披露/终止计算，统一第1条、第12条及通知终止安排。',[evidence(n,'The Receiving Party’s obligation to maintain','will not disclose any trade secrets under this Agreement.'),evidence(n,'12. The term of this Agreement','of this Agreement.')],['最晚何时披露？希望保护多久？预印2025生效年份是否适用于新交易？']))
    g.append(finding('P07-N02','high','知识产权/业务适配','双方承诺不披露trade secrets，不能直接当核心商业秘密交换协议使用','模板一般保密定义较广，但第1条另明确排除计划中的商业秘密披露。拟交换核心算法、源代码或配方时，交易事实可能与该承诺不符；不在此判断美国法上的商业秘密分类。','披露前让相关法域专家判断材料性质；若需交换商业秘密，另行协商匹配的协议/条款与访问机制，不以文件标confidential替代适用性判断。',[evidence(n,'will not disclose any trade secrets under this Agreement.')],['资料是否构成trade secrets？是否仅进行非核心信息的初步讨论？']))
    g.append(finding('P07-N03','medium','信息安全/数据生命周期','档案及备份例外需要可验证的留存期限与限制','第3条已要求备份日常不可访问且后续删除，不宜误报为没有删除义务。但in due course没有具体周期，档案副本也需与第1条有限期限及实际恢复流程协调。','明确留存目的、最长备份轮换周期、受控恢复/再次隔离或删除、访问审计及适当证明；法律留存与技术备份分别约定。',[evidence(n,'3. Confidential Information disclosed','precluded from accessing such information in the ordinary course of business prior to destruction.')],['备份多久覆盖？恢复后如何删除？档案副本谁可访问、保密期后如何处理？']))
    g.append(finding('P07-N04','medium','信息安全/第三方履约','第三方need-to-know已有约束，但责任与事件处置还需匹配风险','第5条明确第三方需知且受保密约束，是现有保护。全文未见可操作的安全事件通报时限、协作/补救流程或明确的第三方违约责任承担方式；这些是否需要取决于信息和接收方环境。','对敏感材料约定获准接收方类别、转交记录、第三方义务传递和违约承担；补充事件通知、控制扩散及协作规则，避免仅依赖reasonable efforts。',[evidence(n,'5. The Receiving Party shall use reasonable efforts','confidentiality agreement with terms at least as restrictive as those herein.')],['related third parties具体包括谁？能否用外部云和AI服务处理？事件责任如何分配？']))
    g.append(finding('P07-N05','high','跨境/出口管制/交易范围','出口受控或涉密材料不在当前交换计划内，修改合同不等于获得监管许可','第15条已明确禁止未经书面修订的受控/涉密材料转移；第11条约定Alabama法。若实际合作跨境或涉及源代码/设备，先核对交易与声明是否一致；未核验出口分类和外国法，不作违法判断。','由具相应法域能力的专家确认参与方、材料分类、访问地点、许可及其他限制，再决定是否能修订/披露；不要把签署修订条款当作监管审批替代。',[evidence(n,'15. No disclosure or transfer','transferred without prior written amendment of this Agreement.'),evidence(n,'11. This Agreement shall be construed','any jurisdiction\'s conflict-of-laws principles.')],['是否有中国或其他境外人员远程访问？材料是否完成出口分类？争议解决场所是否另需明确？']))
    g.append(finding('P07-N06','medium','业务/技术验证/责任','as-is条款适合初步评估，但不能替代交付准确性承诺','第13条对信息准确性/完整性/效用不作保证并排除相关损失责任；第4条不给许可、声明不形成合作关系。若接收方直接用于生产或依赖结果投资，可能超出这份NDA的商业安排。','将用途限定为约定评估；进入测试、采购、研发或许可阶段时另签相应协议，明确可依赖的指标、授权、保证、验收和责任。是否需要调整免责由当地律师确认。',[evidence(n,'13. The CONFIDENTIAL Information','accuracy, completeness, OR utility of the CONFIDENTIAL Information.'),evidence(n,'4. The disclosure of Confidential Information','No license or other right under any U.S. or foreign patent, copyright, or know-how is granted or implied')],['接收方会据此生产部署或作投资决策吗？何时切换到正式研发/许可/采购合同？']))
    reviews=[]
    for ident,text,findings,coverage in [('P05',t,f,{'status':'PARTIAL_AUDIT','read_pages':list(range(1,19)),'unread_pages':list(range(19,105)),'detail':'完整读取页1-18：通知、完整委托开发模板3-16、合作模板封面及说明17-18；其他页仅标题索引，未审核。不得宣称已覆盖8类模板全部内容。'}),('P07',n,g,{'status':'SINGLE_AGENT_TEXT_READ','read_pages':[1,2,3,4],'unread_pages':[],'detail':'全文文字层已读；非六专家四轮，未做全PDF视觉核验/当地法源核验；不保证穷尽风险。'})]:
        reviews.append({'case_id':ident,'input_sha256':hashlib.sha256(text.encode()).hexdigest(),'review_mode':'independent_single_agent_public_template_pilot','coverage':coverage,'stance':'拟使用模板双方的条件性适配检查；未给定具体客户立场','findings':findings,'gold_label_status':'AWAITING_HUMAN_ADJUDICATION'})
    dest=ROOT/'reviews/batch-tech-nda.json';dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps({'reviews':reviews},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'reviews':len(reviews),'findings':sum(len(r['findings']) for r in reviews),'exact_evidence':sum(len(f['evidence']) for r in reviews for f in r['findings'])}))

if __name__=='__main__': main()
