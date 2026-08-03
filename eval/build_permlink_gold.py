"""バッチ1〜6 の判定シートから Zettel 間リンクの正解データを作る（R5 較正用）。

2026-08-02〜03 の大掃除で人間が採否を付けた「Permanent内リンク」提案が、そのまま
「この2本はつながるべき」の教師データになる。採用を正例、却下を負例として書き出す。

使い方:
    .venv/bin/python eval/build_permlink_gold.py

出力: eval/permlink_gold_20260803.json
"""

import json
import re
import sys
from pathlib import Path

VIEWS = Path("/Users/bobtk/pkg_vault/_Reports/review-bundles/2026-08-02_permanent-links/views")
ZETTEL_DIR = Path("/Users/bobtk/pkg_vault/2_Permanent")
OUT = Path(__file__).resolve().parent / "permlink_gold_20260803.json"

HEAD = re.compile(r"^### \d+\.\s*(.+?)\s*(?:（.*）)?\s*$")
PROP = re.compile(r"^\*\*提案\s*([\d-]+)（種別:\s*(.+?)）\*\*")
LINK = re.compile(r"\[\[([^\]|#]+)")


def path_index() -> dict[str, str]:
    """ノート名 → vault ルート相対パス。2_Permanent 配下のみ。"""
    idx: dict[str, str] = {}
    for p in ZETTEL_DIR.rglob("*.md"):
        idx.setdefault(p.stem, str(p.relative_to(ZETTEL_DIR.parent)))
    return idx


def parse(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out, target, cur = [], None, None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = HEAD.match(line)
        if m:
            target, cur = m.group(1), None
            i += 1
            continue
        m = PROP.match(line)
        if m:
            cur = {"sheet": path.name, "no": m.group(1), "kind": m.group(2),
                   "source_title": target, "targets": [], "human": "unresolved"}
            out.append(cur)
            i += 1
            continue
        if cur is not None:
            if line.startswith("```"):
                i += 1
                # 提案本文のコードブロック（最初の1つだけを見る）
                while i < len(lines) and not lines[i].startswith("```"):
                    if not cur["targets"]:
                        cur.setdefault("_block", []).append(lines[i])
                    i += 1
                if not cur["targets"]:
                    block = "\n".join(cur.pop("_block", []))
                    cur["targets"] = LINK.findall(block)
                    cur["after"] = block
            elif line.startswith("- [x] 採用"):
                cur["human"] = "accepted"
            elif line.startswith("- [x] 却下"):
                cur["human"] = "rejected" if cur["human"] != "accepted" else "both"
        i += 1
    return out


def main() -> None:
    if not VIEWS.is_dir():
        sys.exit(f"判定シートが見つからない: {VIEWS}")
    idx = path_index()
    rows = []
    for sheet in sorted(VIEWS.glob("バッチ*.md")):
        rows += parse(sheet)

    perm = [r for r in rows if "Permanent内リンク" in r["kind"]]
    gold, unresolved = [], []
    for r in perm:
        src = idx.get(r["source_title"])
        # 提案行に出てくる [[…]] のうち 2_Permanent 配下に実在するものだけを正解に採る
        tgts = [(t, idx[t]) for t in r["targets"] if t in idx]
        if src is None or not tgts:
            unresolved.append({**r, "reason": "ノート名を解決できない" if src is None
                               else "リンク先が 2_Permanent 配下にない"})
            continue
        gold.append({
            "sheet": r["sheet"], "no": r["no"], "human": r["human"],
            "source_title": r["source_title"], "source_path": src,
            "targets": [{"title": t, "path": p} for t, p in tgts],
        })

    payload = {
        "generated_from": str(VIEWS),
        "note": "大掃除バッチ1〜6 の人間判定。accepted=つなぐべきペア（正例）、rejected=つながない（負例）",
        "counts": {
            "提案（全種別）": len(rows),
            "Permanent内リンク": len(perm),
            "解決できた": len(gold),
            "解決できない": len(unresolved),
            "accepted": sum(1 for g in gold if g["human"] == "accepted"),
            "rejected": sum(1 for g in gold if g["human"] == "rejected"),
            "判定なし・両方チェック": sum(1 for g in gold if g["human"] in ("unresolved", "both")),
        },
        "pairs": gold,
        "unresolved": unresolved,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(payload["counts"], ensure_ascii=False, indent=1))
    for u in unresolved:
        print(f"  未解決: {u['sheet']} 提案{u['no']} {u['source_title']} → {u['targets']}（{u['reason']}）")
    print(f"→ {OUT}")


main()
