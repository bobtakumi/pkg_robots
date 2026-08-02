"""garden stats — 採否の集計（実装プラン M5 の未実装分）。

decisions.jsonl（既存スキーマ・lit_link のみ）と decisions_v2.jsonl（全タイプ）を
突き合わせ、全体と種目別の accepted / rejected / edited 件数と採用率を出す。
v2 に載っているペアは v1 と重複するため、v1 側は「v2 に無いペア」だけ数える
（手書きで decisions.jsonl に足した分＝回収コマンド以前の記録がここに入る）。
"""

import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def collect_rows(root: Path) -> list[dict]:
    proposals = {p["id"]: p for p in load_jsonl(root / "data" / "proposals.jsonl")}
    rows, covered = [], set()
    for d in load_jsonl(root / "data" / "decisions_v2.jsonl"):
        rows.append({"type": d.get("type", "?"), "human": d.get("human", "?"), "src": "v2"})
        p = proposals.get(d["proposal_id"])
        if p and p.get("source_refs"):
            covered.add((p["target"], p["source_refs"][0]))
    for d in load_jsonl(root / "data" / "decisions.jsonl"):
        if (d["zettel_path"], d["lit_path"]) in covered:
            continue
        rows.append({"type": "lit_link", "human": d.get("human", "?"), "src": "v1"})
    return rows


def tally(rows: list[dict]) -> dict:
    t = {"accepted": 0, "rejected": 0, "edited": 0}
    for r in rows:
        if r["human"] in t:
            t[r["human"]] += 1
    adopted = t["accepted"] + t["edited"]
    total = adopted + t["rejected"]
    t["total"] = total
    t["adoption_rate"] = round(adopted / total, 3) if total else 0.0
    return t


def _line(label: str, t: dict) -> str:
    return (f"  {label:<12} 計 {t['total']:>3}（採用 {t['accepted']} / 編集採用 {t['edited']} / "
            f"却下 {t['rejected']}） 採用率 {t['adoption_rate']:.0%}")


def run(cfg: dict, as_json: bool) -> None:
    root: Path = cfg["_root"]
    rows = collect_rows(root)
    types = sorted({r["type"] for r in rows})
    result = {"overall": tally(rows),
              "by_type": {ty: tally([r for r in rows if r["type"] == ty]) for ty in types}}
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return
    if not rows:
        print("採否記録なし（data/decisions.jsonl・decisions_v2.jsonl が空）")
        return
    print("== garden stats == 提案の採用率")
    print(_line("全体", result["overall"]))
    for ty in types:
        print(_line(ty, result["by_type"][ty]))
