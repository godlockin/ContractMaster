"""Development-error-driven training augmentation, without loading held-out text."""
import argparse
import json
import random
from pathlib import Path
from common import rows, messages, spans, digest, dump


def build(output):
    original = rows(Path('artifacts/privacy/data/v3/train.jsonl'))
    public = rows(Path('artifacts/privacy/data/openpii-train/train.jsonl'))
    added = []
    contexts = ["完整通讯地址为{}，请按此送达。", "快递目的地：{}；不得省略行政区域。",
                "送货时请前往{}办理签收。", "交付地点约定在{}，运费另付。",
                "企业住所登记为{}。", "{}为双方确认的收货位置。"]
    for i in range(600):
        city = ['虚构市', '示例市', '临江市', '青浦市', '星州市'][i % 5]
        district = ['松亭区', '望岳区', '书岚区'][i % 3]
        address = f'{city}{district}文星路{i+81000}号{1+i%9}层'
        code = f'北岑专项-{i+81000}'
        text = contexts[i % len(contexts)].format(address)
        entities = [{'text': address, 'type': 'ADDRESS'}]
        if i % 2:
            text += f'本文件涉及内部代号“{code}”，禁止向外披露。'
            entities.append({'text': code, 'type': 'PROJECT'})
        spans(text, entities)
        added.append({'id': f'augmentation-{i}', 'family': f'augmentation-{i%6}',
                      'text': text, 'entities': entities, 'source': 'original-fiction-development-driven'})
    combined = original + added + public
    random.Random(20260917).shuffle(combined)
    dev = rows(Path('artifacts/privacy/data/v3/dev.jsonl'))
    if {digest(r['text']) for r in combined} & {digest(r['text']) for r in dev}:
        raise ValueError('TRAIN_DEV_OVERLAP')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'mlx').mkdir()
    for split, records in [('train', combined), ('valid', dev)]:
        (output / 'mlx' / f'{split}.jsonl').write_text(''.join(
            json.dumps({'messages': messages(r)}, ensure_ascii=False)+'\n' for r in records), encoding='utf-8')
    (output / 'augmentation.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in added), encoding='utf-8')
    dump(output / 'manifest.json', {'recipe': 'address-context-project-v1-public-x1',
         'original_rows': len(original), 'augmentation_rows': len(added), 'public_rows': len(public),
         'training_rows': len(combined), 'training_digest': digest(combined),
         'validation_digest': digest(dev), 'selection_basis': 'v2/v3 development errors only',
         'test_loaded': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
