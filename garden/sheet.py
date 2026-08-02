"""garden sheet — 判定シート生成（拡張プラン R1。旧 report の後継）。

findings（judge の link 判定）を proposals.jsonl に正規化して永続化し、人間が
Obsidian で開いてチェック・微修正して返す「一枚のレビューノート」を書き出す
（設計正本: 2026-07-11 週次庭仕事フロー／体裁は 2026-08-02 大掃除の判定シートの流儀）。

- 1提案 = 見出し → いまの本文 → 貼るだけの提案行 → 根拠 → 採否チェックボックス（1行1個）
- 提案ブロックの直前に `<!-- after: p-… -->`、チェックボックスの直前に `<!-- id: p-… -->` を
  埋める。この2つの目印だけを collect が読む（本文は人間が自由に書き換えてよい）
- 既定の出力先は Vault の `_Reports/`。検証時は必ず `--out` で repo 内に逃がすこと
"""

import json
import re
import sys
import sqlite3
from datetime import date
from pathlib import Path

from . import lint

STATUS_PRIORITY = {"Inbox": 0, "Seeding": 0}  # 7/11 設計: Inbox / Seeding を優先

HEADER = """---
type: report
title: "庭仕事の判定シート {today}"
created: {today}
modified: {today}
tags: [report, PKG運用, garden]
---

# 庭仕事の判定シート {today}

## 30秒で分かる

- 提案 **{n} 件**（{kinds}）。目安 **15分**。判断材料はこのノート内で完結する。
- 各件は「いまの本文 → 貼るだけの提案行 → 根拠」の順。**提案のコードブロックは直接書き換えてよい**。書き換えた版がそのまま採用される。
- 返し方: 各件の末尾で `採用` か `却下` にチェックを1つ入れる。**どちらも空なら保留**で、次回のシートに再掲される。
- 回収: `.venv/bin/python -m garden collect {sheet_name}`（`--dry-run` で内訳だけ確認できる）。
- 並び順は「放置が長い順・Inbox / Seeding 優先」。残りの候補は次回以降へ持ち越す。

---
"""

ENTRY = """
## 提案{n}: [[{ztitle}]] ← [[{link}]]

- 対象: `{target}`（status: {status}・最終編集 {modified}・{days}日放置）
- 種目: 文献リンク（確度 {conf}/5・{relation}・出典 `{lit_path}`）

**いまの本文**

{body_block}

**提案**（この1行を足す。文言はこのブロックを直接書き換えてよい）

<!-- after: {pid} -->
{after_block}

**根拠**

- 接続理由: {rationale}
- Zettel 側: 「{ev_z}」
- 文献側: 「{ev_l}」

<!-- id: {pid} -->
- [ ] 採用
- [ ] 却下
"""


def fence(text: str) -> str:
    """本文に ``` が含まれても壊れないコードブロック。"""
    ticks = "`" * max(3, max((len(m) for m in re.findall(r"`+", text)), default=0) + 1)
    return f"{ticks}md\n{text}\n{ticks}"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def decided_pairs(root: Path) -> set[tuple[str, str]]:
    """採否が記録済みの (zettel_path, lit_path)。decisions.jsonl と decisions_v2 の両方を見る。"""
    pairs = {(d["zettel_path"], d["lit_path"]) for d in load_jsonl(root / "data" / "decisions.jsonl")}
    props = {p["id"]: p for p in load_jsonl(root / "data" / "proposals.jsonl")}
    for d in load_jsonl(root / "data" / "decisions_v2.jsonl"):
        p = props.get(d["proposal_id"])
        if p and p.get("source_refs"):
            pairs.add((p["target"], p["source_refs"][0]))
    return pairs


def decided_ids(root: Path) -> set[str]:
    return {d["proposal_id"] for d in load_jsonl(root / "data" / "decisions_v2.jsonl")}


def link_form(title: str, path: str, idx: dict[str, list[str]]) -> str:
    """wikilink の表記。同名 basename があるときだけパス指定＋別名にして曖昧さを消す。"""
    if len(idx.get(title, [])) > 1:
        return f"{path[:-3]}|{title}"
    return title


def resolve_finding(f: dict, idx: dict[str, list[str]], db_title: dict[str, str]) -> tuple[str, str] | None:
    """findings の1件を (zettel_path, lit_path) に解決する。

    本番 findings は candidates 由来の path を持つ。較正/回帰の findings は
    title しか持たないので、garden.db → Vault の basename 索引の順で引く。
    """
    z = f.get("zettel_path") or db_title.get(f["zettel_title"]) or _first(idx, f["zettel_title"])
    l = f.get("lit_path") or db_title.get(f["lit_title"]) or _first(idx, f["lit_title"])
    return (z, l) if z and l else None


def _first(idx: dict[str, list[str]], title: str) -> str | None:
    paths = idx.get(title)
    return paths[0] if paths else None


def db_titles(cfg: dict) -> dict[str, str]:
    db = cfg["_root"] / cfg["index"]["db_path"]
    if not db.exists():
        return {}
    con = sqlite3.connect(db)
    try:
        return {t: p for t, p in con.execute("SELECT title, path FROM notes")}
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()


def next_id(existing: list[dict], batch: str) -> int:
    n = 0
    for p in existing:
        m = re.match(rf"p-{batch}-(\d+)$", p["id"])
        if m:
            n = max(n, int(m.group(1)))
    return n + 1


def build_proposals(cfg: dict, findings: list[dict], notes: list[dict]) -> tuple[list[dict], list[dict]]:
    """findings（link 判定）を proposals に正規化。既に採否記録済みのペアは落とす。"""
    root: Path = cfg["_root"]
    idx = lint.title_index(notes)
    by_path = {n["path"]: n for n in notes}
    existing = load_jsonl(root / "data" / "proposals.jsonl")
    known = {(p["target"], p["source_refs"][0]) for p in existing if p.get("source_refs")}
    decided = decided_pairs(root)
    batch = date.today().strftime("%Y%m%d")
    seq = next_id(existing, batch)
    db_title = db_titles(cfg)

    fresh = []
    for f in findings:
        pair = resolve_finding(f, idx, db_title)
        if pair is None or pair in decided or pair in known:
            continue
        z_path, l_path = pair
        if z_path not in by_path or l_path not in by_path:
            continue
        known.add(pair)
        link = link_form(by_path[l_path]["title"], l_path, idx)
        fresh.append({
            "id": f"p-{batch}-{seq:03d}",
            "type": "lit_link",
            "target": z_path,
            "before": None,
            "after": f"- [[{link}]]（{f.get('relation', '関連')}）",
            "rationale": f.get("reason", ""),
            "source_refs": [l_path],
            "batch": batch,
            "proposer": "connector",
            "confidence": f.get("confidence"),
            "evidence_zettel": f.get("evidence_zettel", ""),
            "evidence_lit": f.get("evidence_lit", ""),
        })
        seq += 1
    return existing, fresh


def order_key(p: dict, by_path: dict[str, dict], today: date):
    """放置が長い順・Inbox / Seeding 優先（7/11 設計の優先度選定）。"""
    n = by_path.get(p["target"], {})
    mod = n.get("modified") or date.fromtimestamp(n.get("mtime", 0)) if n else None
    days = (today - mod).days if mod else 0
    return (STATUS_PRIORITY.get(n.get("status", ""), 1), -days)


def _relation(after: str) -> str:
    m = re.search(r"（([^（）]*)）\s*$", after)
    return m.group(1) if m else "関連"


def render(cfg: dict, picked: list[dict], notes: list[dict], sheet_name: str, today: date) -> str:
    by_path = {n["path"]: n for n in notes}
    parts = [HEADER.format(today=today.isoformat(), n=len(picked),
                           kinds="文献リンク", sheet_name=sheet_name)]
    for i, p in enumerate(picked, 1):
        n = by_path[p["target"]]
        lit = by_path[p["source_refs"][0]]
        mod = n["modified"] or date.fromtimestamp(n["mtime"])
        parts.append(ENTRY.format(
            n=i, ztitle=n["title"], link=lit["title"], target=p["target"],
            status=n["status"] or "（欠落）", modified=mod.isoformat(), days=(today - mod).days,
            conf=p.get("confidence", "?"), relation=_relation(p["after"]),
            lit_path=p["source_refs"][0],
            body_block=fence(n["body"].strip()), after_block=fence(p["after"]), pid=p["id"],
            rationale=p["rationale"], ev_z=p["evidence_zettel"], ev_l=p["evidence_lit"]))
    parts.append("\n---\n\n判定を書き終えたら回収コマンドを実行する。"
                 "チェックが両方空の提案は保留として `data/proposals.jsonl` に残り、次回のシートに再掲される。\n")
    return "".join(parts)


def run(cfg: dict, findings_path: Path | None, out: Path | None) -> None:
    root: Path = cfg["_root"]
    src = findings_path or (root / "data" / "findings.json")
    if not src.exists():
        sys.exit(f"findings が見つからない: {src}（先に garden judge を実行するか --findings で指定）")
    findings = json.loads(src.read_text(encoding="utf-8"))
    min_conf = cfg.get("report", {}).get("min_confidence", 5)
    links = [f for f in findings
             if f.get("verdict") == "link" and f.get("confidence", 0) >= min_conf]
    links.sort(key=lambda f: (-f.get("confidence", 0), -f.get("score", 0)))

    notes = lint.load_notes(cfg)
    existing, fresh = build_proposals(cfg, links, notes)
    if fresh:
        with (root / "data" / "proposals.jsonl").open("a", encoding="utf-8") as fp:
            for p in fresh:
                fp.write(json.dumps(p, ensure_ascii=False) + "\n")

    # 保留（未採否）の既存提案を先に、今回の新規を後に。target が Vault から消えたものは落とす
    by_path = {n["path"]: n for n in notes}
    done, decided = decided_ids(root), decided_pairs(root)
    pending = [p for p in existing + fresh
               if p["id"] not in done and p["target"] in by_path
               and p.get("source_refs", [""])[0] in by_path
               and (p["target"], p["source_refs"][0]) not in decided]
    today = date.today()
    pending.sort(key=lambda p: order_key(p, by_path, today))
    cap = cfg.get("sheet", {}).get("max_proposals", 5)
    picked = pending[:cap]
    if not picked:
        print(f"提案0件（confidence>={min_conf} の link {len(links)} 件・"
              f"保留 {len(pending)} 件）。シートは生成しない")
        return

    name = f"garden-weekly-{today.strftime('%Y%m%d')}.md"
    dest = out or (Path(cfg["vault"]["path"]) / "_Reports" / name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render(cfg, picked, notes, str(dest), today), encoding="utf-8")
    print(f"提案 {len(picked)} 件（新規 {len(fresh)}・保留繰越 {len(pending) - len(fresh)}・"
          f"上限 {cap}）→ {dest}")
    if len(pending) > cap:
        print(f"次回持ち越し {len(pending) - cap} 件（少数・非一括の原則）")
