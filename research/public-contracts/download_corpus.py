"""Download a fixed public-template corpus; no private contract inputs supported."""
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import urllib.request

ROOT = Path(__file__).resolve().parent
HENAN = 'https://luohe.zfcg.henan.gov.cn/henan/content?channelCode=H670402&infoId=1746604904828872'
BASE = 'https://luohe.zfcg.henan.gov.cn/webfile/hebi/rootfiles/2025/06/04/'
CASES = [
 ('P01','济宁市劳动合同示范文本（2019版）','劳动用工','zh-CN','中国山东；空白劳动合同，含劳务派遣分支；历史版本用于核验适用时点', 'https://hrss.jining.gov.cn/art/2019/5/14/art_18525_1465214.html', 'https://hrss.jining.gov.cn/module/download/downfile.jsp?classid=0&filename=c620ab6aa0e6421399d6092766b0c20f.pdf'),
 ('P02','政府采购合同示范文本（货物）','货物采购','zh-CN','中国；政府采购货物及通用/专用条款',HENAN,BASE+'1746604904828872-1748910942432566.pdf'),
 ('P03','政府采购合同示范文本（服务）','公共服务采购','zh-CN','中国；政府采购服务及通用/专用条款',HENAN,BASE+'1746604904828872-1748910942433280.pdf'),
 ('P04','建设工程施工合同示范文本','建设工程','zh-CN','中国；长合同、协议书/通用/专用/附件优先关系',HENAN,BASE+'1746604904828872-1748910942443482.pdf'),
 ('P05','技术开发合同示范文本（填写样例）','软件研发与知识产权','zh-CN','中国上海；银行会计软件研发填写示例，2003版表式/2011年示例，非真实签署合同','https://kyc.stiei.edu.cn/_upload/article/files/5c/16/f9865f0446cc982ad5921cadcb40/dac2dbed-131b-458e-a301-27dfd3baca94.pdf','https://kyc.stiei.edu.cn/_upload/article/files/5c/16/f9865f0446cc982ad5921cadcb40/dac2dbed-131b-458e-a301-27dfd3baca94.pdf'),
 ('P06','Agreement for Consulting Services','设计咨询与保险','en','美国密苏里；高校工程设计咨询；公共机构单方模板','https://design.missouristate.edu/_Files/ConsultingAgreements/AgreementforConsultingServices.pdf','https://design.missouristate.edu/_Files/ConsultingAgreements/AgreementforConsultingServices.pdf'),
 ('P07','Mutual Nondisclosure Agreement','保密与科研合作','en','美国高校公开双向NDA；公司与科研人员；短合同','https://web.stanford.edu/group/OTL/documents/mutualNDA.pdf','https://web.stanford.edu/group/OTL/documents/mutualNDA.pdf'),
 ('P08','郑州市住房租赁合同范本','住房租赁','zh-CN','中国河南郑州；2025公开住宅租赁空白模板','https://zfbzj.zhengzhou.gov.cn/notice/9223797.jhtml','https://zfbzj.zhengzhou.gov.cn/attachment/%E9%83%91%E5%B7%9E%E5%B8%82%E4%BD%8F%E6%88%BF%E7%A7%9F%E8%B5%81%E5%90%88%E5%90%8C%E8%8C%83%E6%9C%AC.pdf?x0dQhlSUGklU0M-6WKkLsBY2vKp37Pp-9Y3atjXF5DYHaQEIktxPw0dCMYbV5ZnGyYjPu3Q3DqkF5HwB_Pi_CE0vCQ=='),
]
CASES[4] = ('P05','科技部技术合同示范文本汇编（2001）','研发与知识产权','zh-CN','中国；104页8类模板汇编，委托/合作开发、专利申请权/专利权/实施许可/技术秘密转让、咨询、服务；不是单份已签合同；历史合同法引用需时效核验','https://kjc.neuq.edu.cn/system/resource/storage/download.jsp?mark=OUZDNDY0Q0EzQzEyOUNBMzJDREYwNTYxQ0Y3QUVFNjYvMjA3NEMxNUQvMTBERkFG','https://kjc.neuq.edu.cn/system/resource/storage/download.jsp?mark=OUZDNDY0Q0EzQzEyOUNBMzJDREYwNTYxQ0Y3QUVFNjYvMjA3NEMxNUQvMTBERkFG')
CASES[6] = ('P07','Auburn Mutual Nondisclosure Agreement','保密与科研合作','en','美国阿拉巴马；高校双向NDA，包含出口管制及备份保留；模板v1.31.24，生效栏预印2025需核验','https://research.auburn.edu/_assets/nda-template1.pdf','https://research.auburn.edu/_assets/nda-template1.pdf')

def fetch(case, root=ROOT, expected_sha256=None):
    ident,title,domain,language,scope,page,url = case
    record = dict(zip(('id','title','domain','language','scope','source_page','download_url'),case))
    record.update(downloaded_at=datetime.now(timezone.utc).isoformat(),license_notes='公开提供查阅/下载；未核实独立再分发或模型训练许可。仅本地授权评测；公开来源不是法律无风险证明。')
    try:
        from pypdf import PdfReader
        original=root/'originals'/f'{ident}.pdf'
        if original.exists():
            data=original.read_bytes()
            record['resolved_url']=url
            record['processed_at']=record['downloaded_at']
            record['downloaded_at']=datetime.fromtimestamp(original.stat().st_mtime,timezone.utc).isoformat()
        else:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 Contract-Review-Public-Template-Research'})
            with urllib.request.urlopen(req,timeout=60) as response:
                data=response.read(30_000_001)
                record['resolved_url']=response.url
        if len(data)>30_000_000 or not data.startswith(b'%PDF'):
            raise ValueError('Response not PDF or exceeded 30MB limit')
        if expected_sha256 and hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError('Original hash changed; explicit corpus revision required')
        if not original.exists(): original.write_bytes(data)
        reader=PdfReader(original)
        pages=[p.extract_text() or '' for p in reader.pages]
        text='\n\n'.join(f'[PAGE {i+1}]\n{p}' for i,p in enumerate(pages))
        textpath=root/'text'/f'{ident}.txt'; textpath.write_text(text,encoding='utf-8')
        replacements={}
        def mask(match):
            value=match.group(0)
            if value not in replacements: replacements[value]=f'[PUBLIC_CONTACT_{len(replacements)+1:03}]'
            return replacements[value]
        sanitized=re.sub(r'高少峰|Patrick\s+E\.\s+Reed|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)|(?<!\d)\d{17}[\dXx](?!\d)|(?<!\d)(?:0\d{2,3}[-－ ]\d{7,8}|\(?\d{3}\)?[- ]\d{3}[- ]\d{4})(?!\d)',mask,text)
        sanitizedpath=root/'sanitized'/f'{ident}.txt'; sanitizedpath.write_text(sanitized,encoding='utf-8')
        mapping=root/'private'/f'{ident}-mapping.json'; mapping.write_text(json.dumps(replacements,ensure_ascii=False,indent=2),encoding='utf-8'); mapping.chmod(0o600)
        record.update(original_path=original.relative_to(root).as_posix(),text_path=textpath.relative_to(root).as_posix(),sanitized_path=sanitizedpath.relative_to(root).as_posix(),sha256=hashlib.sha256(data).hexdigest(),sanitized_sha256=hashlib.sha256(sanitized.encode()).hexdigest(),page_count=len(pages),character_count=len(text),extraction_status='TEXT_EXTRACTED_LAYOUT_NOT_VERIFIED',extraction_gaps={'empty_pages':[i+1 for i,p in enumerate(pages) if not p.strip()],'images_per_page':[len(p.images) for p in reader.pages],'notice':'PDF文字层提取不证明版面/表格/手写/图像完整；页面标记为派生定位，不是原文。'},privacy_status='PUBLIC_TEMPLATE_REGEX_SCREENED_NOT_PRIVATE_RELEASE',masked_count=len(replacements),download_status='DOWNLOADED')
    except Exception as exc:
        record.update(download_status='FAILED',error=f'{type(exc).__name__}: {exc}')
    return record

def local_record(record):
    ident = record['id']
    return {**record, 'original_path': f'originals/{ident}.pdf',
            'text_path': f'text/{ident}.txt', 'sanitized_path': f'sanitized/{ident}.txt'}


def locally_ready(root, record):
    if not record or record.get('download_status') != 'DOWNLOADED':
        return False
    local = local_record(record)
    required = [root / local[key] for key in ('original_path', 'text_path', 'sanitized_path')]
    required.append(root / 'private' / f"{record['id']}-mapping.json")
    try:
        return all(path.is_file() for path in required) and all(
            hashlib.sha256((root / local[path_key]).read_bytes()).hexdigest() == record.get(hash_key)
            for path_key, hash_key in (('original_path', 'sha256'), ('sanitized_path', 'sanitized_sha256')))
    except OSError:
        return False


def main(root=ROOT, cases=CASES, fetcher=None):
    for folder in ('originals','text','sanitized','private'): (root/folder).mkdir(parents=True,exist_ok=True)
    (root/'private').chmod(0o700)
    old=json.loads((root/'manifest.json').read_text()) if (root/'manifest.json').exists() else {'cases':[]}
    prior={c['id']:c for c in old['cases']}
    failed=[c for c in old['cases'] if c['download_status']=='FAILED']
    if failed:
        with (root/'download-failures.jsonl').open('a',encoding='utf-8') as out:
            for c in failed: out.write(json.dumps(c,ensure_ascii=False)+'\n')
    todo=[c for c in cases if not locally_ready(root, prior.get(c[0]))]
    if fetcher is None:
        fetcher = lambda case: fetch(case, root, prior.get(case[0], {}).get('sha256'))
    with ThreadPoolExecutor(max_workers=4) as pool: fresh={r['id']:r for r in pool.map(fetcher,todo)}
    results=[]
    for case in cases:
        ident = case[0]
        previous = prior.get(ident, {})
        current = fresh.get(ident, previous)
        # Attempt failures must never erase the last known corpus identity.
        if current.get('download_status') == 'FAILED':
            current = {**previous, **current}
            for key in ('sha256', 'sanitized_sha256'):
                if key in previous:
                    current[key] = previous[key]
        results.append(local_record(current))
    (root/'manifest.json').write_text(json.dumps({'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),'purpose':'User-authorized public-template review tests; not private-client release; no lawyer gold labels','cases':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{'id':r['id'],'status':r['download_status'],'pages':r.get('page_count'),'chars':r.get('character_count'),'masked':r.get('masked_count'),'error':r.get('error')} for r in results],ensure_ascii=False))
    return 0 if all(r['download_status'] == 'DOWNLOADED' for r in results) else 2

if __name__=='__main__': raise SystemExit(main())
