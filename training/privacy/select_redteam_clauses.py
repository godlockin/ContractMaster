"""Select grounded business clauses, excluding cover sheets and instructions."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANCHORS = {'P01': '第十九条', 'P02': '（2）付款方式', 'P03': '第五条 付款方式',
           'P04': '3.2.2 项目经理', 'P06': 'Compensation for Basic Services shall',
           'P07': '1. The Receiving Party shall', 'P08': '第三条 租金及押金'}


def build(source_path: Path, output: Path):
    document = json.loads(source_path.read_text())
    selected = []
    for source in document['sources']:
        if not source.get('structure_excerpt') or source.get('verification_errors'):
            continue
        text_path = ROOT / source['local_text_path']
        text = text_path.read_text()
        sid = source['source_id']
        if sid.startswith('P05-'):
            pages = list(re.finditer(r'\[PAGE (\d+)\]', text))
            first, last = source['section_pages']
            lower = next(m.start() for m in pages if int(m[1]) == first)
            upper = next((m.start() for m in pages if int(m[1]) == last + 1), len(text))
            segment = text[lower:upper]
            clauses = list(re.finditer(r'第[一二三四五六七八九十]+条[：:\s]', segment))
            candidates = [m for i, m in enumerate(clauses) if re.search(
                '保密|支付|违约', segment[m.start():clauses[i+1].start() if i+1<len(clauses) else len(segment)])]
            start = lower + candidates[0].start()
        else:
            start = text.index(ANCHORS[sid])
            upper = len(text)
        end = min(start + 1400, upper)
        excerpt = ' '.join(text[start:end].split())[:300]
        selected.append({**source, 'structure_excerpt': excerpt, 'substantive_excerpt': excerpt,
                         'excerpt_raw_char_range': [start, end],
                         'excerpt_page': text[:start].count('[PAGE '),
                         'excerpt_local_text_sha256': hashlib.sha256(text_path.read_bytes()).hexdigest()})
    output.mkdir(parents=True, exist_ok=False)
    (output/'sources.json').write_text(json.dumps({**document, 'sources': selected}, ensure_ascii=False, indent=2))
    print(json.dumps({'templates': len(selected), 'selection': 'business_clause_anchors'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.sources, args.output)
