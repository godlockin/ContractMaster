"""Render repair-v6 data from reviewed template specification."""
from __future__ import annotations
import argparse, hashlib, json, re
from collections import Counter
from pathlib import Path
from common import digest, messages

SPLIT_COUNTS = {"train": 100, "dev": 32, "holdout": 40}
SENSITIVE = {"PERSON":"PERSON", "EMAIL":"EMAIL", "SECRET":"SECRET", "PRIVATE_AMOUNT":"SECRET", "ADDRESS":"ADDRESS", "ACCOUNT":"ACCOUNT", "PROJECT":"PROJECT"}
PRESERVE = {"PUBLIC_AMOUNT", "BILLING_AMOUNT", "VERSION", "PROJECT"}
PLACEHOLDER = re.compile(r"<([A-Z][A-Z_]*)>")

def _values(split: str, n: int) -> dict[str, str]:
    tag = {"train":"TR", "dev":"DV", "holdout":"HO"}[split]
    base = {"train": 10000, "dev": 20000, "holdout": 30000}[split] + n
    surnames = "翟窦郜蔺郝仇靳邴阮裴"
    given = "澜砚棠槐弈岑璟翎绮昀珩琬蘅芮晏颐湛骞翊颢"
    person_index = ({"train": 0, "dev": 100, "holdout": 140}[split] + n)
    person = surnames[person_index // 20] + given[(person_index % 20)] + given[(person_index * 7) % 20] + given[(person_index * 11) % 20]
    regions = ("东浦", "南溪", "西岭", "北湾", "云河", "青岚")
    return {"PERSON":person, "EMAIL":f"liaison.{tag.lower()}{n:03d}@example.invalid", "SECRET":f"K6-{tag}-{n:03d}-Q", "PRIVATE_AMOUNT":f"{base+17}万元", "PUBLIC_AMOUNT":f"{base+71}万元", "BILLING_AMOUNT":f"{base%1000+3}.8万元", "ADDRESS":f"{regions[n%len(regions)]}区云杉路{base+8}号", "ACCOUNT":f"62170088{base:08d}", "PROJECT":f"内部项目-{tag}-{n:03d}", "PUBLIC_PROJECT":f"公开项目-{tag}-{n:03d}", "ORDER":f"订单-{tag}-{n:03d}", "VERSION":f"v6.{base}.{(base+1)%100}"}

def _render(template: str, values: dict[str, str]) -> tuple[str, list[str]]:
    used: list[str] = []
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values: raise ValueError(f"UNKNOWN_PLACEHOLDER:{key}")
        used.append(key); return values[key]
    return PLACEHOLDER.sub(repl, template), used

def _attack(text: str, entities: list[dict[str,str]], preserve: list[str], method: str) -> tuple[str,list[dict[str,str]],list[str],list[str]]:
    methods: list[str] = []
    trans = str.maketrans("0123456789", "０１２３４５６７８９")
    if method == "person_slash" and any(e["type"] == "PERSON" for e in entities):
        for e in entities:
            if e["type"] == "PERSON":
                attacked = " / ".join(e["text"]); text = text.replace(e["text"], attacked); e["text"] = attacked
        methods.append(method)
    elif method == "account_grouping" and any(e["type"] == "ACCOUNT" for e in entities):
        for e in entities:
            if e["type"] == "ACCOUNT":
                attacked = " ".join(e["text"][i:i+4] for i in range(0,len(e["text"]),4)); text=text.replace(e["text"],attacked); e["text"]=attacked
        preserve = [v for v in preserve]; methods.append(method)
    elif method == "unicode_escape" and any(e["type"] == "SECRET" for e in entities):
        for e in entities:
            if e["type"] == "SECRET":
                attacked = "".join(f"\\u{ord(ch):04x}" for ch in e["text"]); text=text.replace(e["text"],attacked); e["text"]=attacked
        preserve = [v for v in preserve]; methods.append(method)
    if method == "fullwidth_digits" or not methods:
        text=text.translate(trans); entities=[{"text":e["text"].translate(trans),"type":e["type"]} for e in entities]; preserve=[v.translate(trans) for v in preserve]; methods.append("fullwidth_digits")
    return text, entities, preserve, methods

def _row(split: str, template: dict, index: int, role: str, variant: str) -> dict:
    values = _values(split,index)
    if role == "negative": values["PROJECT"] = values["PUBLIC_PROJECT"]
    text, used = _render(template[role],values); entities=[]; preserve=[]
    for key in used:
        value=values[key]
        kind=SENSITIVE.get(key)
        if key in PRESERVE and not (role == "positive" and key == "PROJECT") and value not in preserve: preserve.append(value)
        if kind and not (role == "negative" and key == "PROJECT"):
            item={"text":value,"type":kind}
            if item not in entities: entities.append(item)
    methods=[]
    if variant == "attack":
        # Select an operation supported by this template, keeping all four
        # attack families represented in the rendered corpus.
        method = ("account_grouping" if "<ACCOUNT>" in template[role] else
                  "unicode_escape" if "<SECRET>" in template[role] else
                  "person_slash" if "<PERSON>" in template[role] else
                  "fullwidth_digits")
        text,entities,preserve,methods=_attack(text,entities,preserve,method)
    spans=[]
    for e in entities: spans.extend({"start":m.start(),"end":m.end(),"text":e["text"],"type":e["type"]} for m in re.finditer(re.escape(e["text"]),text))
    pair=f"R6-{split[:2].upper()}-{index:03d}-{role[0].upper()}"
    row={"id":f"{pair}-{role[0]}-{variant}","pair_id":pair,"minimal_pair_id":f"R6-M-{split[:2].upper()}-{index:03d}","variant":variant,"pair_role":role,"attack_type":methods[0] if methods else None,"attack_methods":methods,"industry":template["industry"],"template_id":template["id"],"text":text,"entities":entities,"gold_spans":spans,"scoring_scope":[0,len(text)],"preserve_literals":preserve,"invariant_components":[],"source_kind":"synthetic","train_allowed":split!="holdout","provenance":{"generator":"repair-v6-template-spec-v3","template_hash":hashlib.sha256(template[role].encode()).hexdigest(),"text_hash":hashlib.sha256(text.encode()).hexdigest()}}
    if not entities: row["preserve_text"]=text
    return row

def build(spec_path: Path, output: Path) -> None:
    if output.exists(): raise FileExistsError(f"OUTPUT_EXISTS:{output}")
    spec=json.loads(spec_path.read_text(encoding="utf-8")); templates=spec.get("templates")
    if spec.get("schema_version") != 3 or not isinstance(templates,list) or len(templates)!=24: raise ValueError("SPEC_SCHEMA")
    by_split={s:[t for t in templates if t.get("split")==s] for s in SPLIT_COUNTS}
    if any(len(v)!=8 for v in by_split.values()): raise ValueError("SPEC_SPLIT_TEMPLATE_COUNT")
    output.mkdir(parents=True); (output/"mlx").mkdir(); all_rows={}; stats=Counter()
    for split,count in SPLIT_COUNTS.items():
        rows=[_row(split,by_split[split][i%8],i,role,var) for i in range(count) for role in ("positive","negative") for var in ("clean","attack")]; all_rows[split]=rows
        for row in rows: stats.update(row["attack_methods"])
        (output/f"{split}.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")
        if split != "holdout": (output/"mlx"/("train.jsonl" if split=="train" else "valid.jsonl")).write_text("".join(json.dumps({"messages":messages(r)},ensure_ascii=False)+"\n" for r in rows),encoding="utf-8")
    manifest={"schema_version":4,"generator":"build_repair_v6_spec.py","template_spec":str(spec_path),"template_spec_sha256":hashlib.sha256(spec_path.read_bytes()).hexdigest(),"rows":{k:len(v) for k,v in all_rows.items()},"pair_counts":{k:len(v)//4 for k,v in all_rows.items()},"unique_ids":len({r["id"] for rs in all_rows.values() for r in rs}),"unique_texts":len({r["text"] for rs in all_rows.values() for r in rs}),"template_skeletons":len({r["template_id"] for rs in all_rows.values() for r in rs}),"gold_spans":sum(len(r["gold_spans"]) for rs in all_rows.values() for r in rs),"preserve_literals":sum(len(r["preserve_literals"]) for rs in all_rows.values() for r in rs),"attack_methods":dict(sorted(stats.items())),"digests":{k:digest(v) for k,v in all_rows.items()},"holdout_sha256":hashlib.sha256((output/"holdout.jsonl").read_bytes()).hexdigest()}
    (output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--spec",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); build(a.spec,a.output); print(json.dumps({"status":"BUILT","output":str(a.output)},ensure_ascii=False))
if __name__ == "__main__": main()
