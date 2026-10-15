"""Build a deterministic cross-source attack matrix from verified template inventory."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from common import spans, digest
from redteam_attack_catalog import specifications


def build(source_path: Path, output: Path, contexts_per_attack: int = 6):
    document = json.loads(source_path.read_text())
    sources = document['sources']
    usable = [s for s in sources if s.get('structure_excerpt') and
              not s.get('verification_errors') and s.get('verification_status') not in {'FAILED','UNVERIFIED'}]
    if not usable:
        raise ValueError('NO_VERIFIED_SOURCE_CONTEXT')
    specs = specifications()
    rows = []
    layout_names = ('clause','markdown_table','numbered_annex','xml_fields')
    def wrap(text, layout):
        if layout=='markdown_table':
            return '| 条款 | 内容 |\n| --- | --- |\n| 待审内容 | '+text+' |'
        if layout=='numbered_annex':
            return '附件：合同补充约定\n第一项\n'+text+'\n本附件与主合同具有同等效力。'
        if layout=='xml_fields':
            return '<contract><clause><![CDATA['+text+']]></clause></contract>'
        return text
    for index,spec in enumerate(specs):
        if spec['clean']==spec['attack']:
            raise ValueError('IDENTITY_ATTACK')
        for offset in range(min(contexts_per_attack,len(usable))):
            source = usable[(index+offset)%len(usable)]
            source_id = source['source_id']
            layout = layout_names[(index+offset)%len(layout_names)]
            prefix = source['structure_excerpt'][:300]+'\n【虚构鲁棒性测试填充条款】\n'
            pair_id=f'M3-{index:03d}-{source_id}-{layout}'
            for variant in ('clean','attack'):
                payload = wrap(spec[variant],layout)
                entities=[{'text':value,'type':kind} for value,kind in spec[variant+'_entities']]
                spans(payload,entities)
                text=prefix+payload
                row=dict(id=pair_id+'-'+variant,pair_id=pair_id,variant=variant,attack_type=spec['category'],
                    text=text,entities=entities,scoring_scope=[len(prefix),len(text)],source_id=source_id,
                    source_url=source.get('source_page',source.get('url')),
                    industry=source.get('industry',source.get('domain','unspecified')),
                    scenario=source.get('scenario',source.get('title')),
                    layout=layout,source_format=source.get('format','unknown'),train_allowed=False,
                    preserve_literals=spec.get('preserve',[]) if variant=='attack' else [])
                if not entities:
                    row['preserve_payload']=payload
                rows.append(row)
    if len({r['id'] for r in rows})!=len(rows):
        raise ValueError('DUPLICATE_ROW_ID')
    output.mkdir(parents=True,exist_ok=False)
    (output/'test.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    attacks=[r for r in rows if r['variant']=='attack']
    coverage={field:dict(Counter(r[field] for r in attacks)) for field in
              ('attack_type','source_id','industry','scenario','layout','source_format')}
    manifest=dict(rows=len(rows),pairs=len(attacks),attack_specifications=len(specs),
        unique_texts=len({r['text'] for r in rows}),source_templates=len(usable),
        contexts_per_attack=contexts_per_attack,coverage=coverage,data_digest=digest(rows),
        source_manifest_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),train_allowed=False,
        limits=['Partial combinatorial matrix, not every attack against every source.',
                'Text layouts are not physical file formats; separate format fixtures test extraction.',
                'Scores cover injected annotated payload only, not unlabelled source background.'])
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in manifest.items() if k!='coverage'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--contexts',type=int,default=6)
    args=parser.parse_args()
    build(args.sources,args.output,args.contexts)
