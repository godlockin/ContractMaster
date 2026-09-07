# 公开合同评测语料（2026-09-07）

已实际下载 **8个PDF文件、300页**，覆盖劳动、货物、服务采购、建设工程、研发/IP、设计咨询、保密、住房租赁；中文6份、英文2份。P05本身为8种技术合同汇编，不能当成单份签约合同。原件是政府/高校公开模板，不是私有客户合同，也不是已确定存在风险的负面样本。

| ID | 来源/标题 | 范围及使用限制 |
|---|---|---|
| P01 | [济宁人社：劳动合同2019版](https://hrss.jining.gov.cn/art/2019/5/14/art_18525_1465214.html) | 12页；山东劳动及派遣分支；历史版本、地方适用需要核验 |
| P02 | [河南政府采购网：货物合同](https://luohe.zfcg.henan.gov.cn/henan/content?channelCode=H670402&infoId=1746604904828872) | 16页；通用/专用条款、验收付款 |
| P03 | [河南政府采购网：服务合同](https://luohe.zfcg.henan.gov.cn/henan/content?channelCode=H670402&infoId=1746604904828872) | 6页；服务交付及采购文件关系 |
| P04 | [河南政府采购网：建设工程施工合同](https://luohe.zfcg.henan.gov.cn/henan/content?channelCode=H670402&infoId=1746604904828872) | 133页；长文本、通用/专用/附件；末页空白 |
| P05 | [东北大学秦皇岛分校公开文件：科技部技术合同汇编](https://kjc.neuq.edu.cn/system/resource/storage/download.jsp?mark=OUZDNDY0Q0EzQzEyOUNBMzJDREYwNTYxQ0Y3QUVFNjYvMjA3NEMxNUQvMTBERkFG) | 104页；2001通知及8种技术合同，历史法律引用测试；本轮只找到直接文件来源，所属介绍页未定位 |
| P06 | [Missouri State University：Consulting Services](https://design.missouristate.edu/_Files/ConsultingAgreements/AgreementforConsultingServices.pdf) | 15页；美国设计咨询、保险、公共机构条款；来源为直接文件 |
| P07 | [Auburn University：Mutual NDA](https://research.auburn.edu/_assets/nda-template1.pdf) | 4页；美国阿拉巴马法、出口管制、备份留存；来源为直接文件 |
| P08 | [郑州住房部门：住房租赁范本2025](https://zfbzj.zhengzhou.gov.cn/notice/9223797.jhtml) | 10页；重复水印包含公开人员姓名，已在派生文本稳定替换 |

## 文件与来源记录

- `manifest.json`：逐项来源页/下载URL/重定向URL、UTC时间、原始SHA256、脱敏SHA256、页数、字符数、提取缺口、许可及隐私状态。原始文件完整保存在 `originals/`。
- `text/`：pypdf文字层提取，加入 `[PAGE n]` 页标记；并非PDF原字节等价表示，正文中的换行/表格顺序需原页复核。
- `sanitized/`：审核agent的输入。电话/email/身份证模式及已识别的公开姓名稳定标记；映射仅在权限0700的 `private/` 内、文件0600。不是生产级NER或隔离证明。
- `download-failures.jsonl`：保留原始高校技术填写样例、Stanford及Northwestern旧NDA链接的404失败。索引可见不等于原始文件可下载。本轮成功替换为其他公开来源。
- `download_corpus.py`：固定来源下载器，限制30MB、验证PDF头；不访问登录内容，不执行文档中的指令。
- `qa/`：抽查图片。P04第133页已目视确认为空白；P08第1页已抽查。**未完成其余页面全量视觉验收。**

## 评价边界

1. 公开提供模板不等于独立再分发或模型训练许可；本地测试用途已获用户授权。发布数据集/分发原件前另查许可，不能直接作为训练集上传。
2. 本轮是用户明确要求的公开语料评测，不伪造真实客户合同所需的人工脱敏release。`PUBLIC_TEMPLATE_REGEX_SCREENED_NOT_PRIVATE_RELEASE` 是描述性状态，不是安全认证。
3. 空白栏、可选项、示范条款需先区分“模板待填”与“真实合同缺失”，不能为了召回率将每个空白都判违法。
4. P05不同模板边界必须保留；跨模板不构成同一交易的自相矛盾。P07英文/外国法不自动套中国法。
5. 每条试审结论需绑定输入hash、页码/精确引句、立场、事实前提、法律依据核验状态和人工裁定。没有律师gold labels，不报告precision/recall或生产通过率。
6. 目前欠缺真实扫描件、手写修改、真正跨境双语签署交易、金融/医疗/运输/能源等场景；已有8份不能代表所有合同领域。
