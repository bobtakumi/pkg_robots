"""garden sheet — 判定シート生成（拡張プラン R1。旧 report の後継）。

findings（judge の link 判定）を proposals.jsonl に正規化して永続化し、人間が
Obsidian で開いてチェック・微修正して返す「一枚のレビューノート」を書き出す
（設計正本: 2026-07-11 週次庭仕事フロー／体裁は 2026-08-02 大掃除の判定シートの流儀）。

- 1提案 = 見出し → いまの本文 → 貼るだけの提案行 → 根拠 → 採否チェックボックス（1行1個）
- 提案ブロックの直前に `<!-- after: p-… -->`、チェックボックスの直前に `<!-- id: p-… -->` を
  埋める。この2つの目印だけを collect が読む（本文は人間が自由に書き換えてよい）
- 既定の出力先は Vault の `_Reports/`。検証時は必ず `--out` で repo 内に逃がすこと

載せる種目は3系統。connector 由来の文献リンク（findings 経由）、rules 由来の規則ベース
提案（R4: 成熟度・タグ・起票待ちキュー）、permlink 由来の Zettel 間リンク（R5: 構造と語彙だけ）。
findings が無い環境（判定 LLM に届かない Mac 等）でも rules と permlink だけでシートは生える。

提案本文の書き方（2026-08-03 バッチ2 の返却で確定・複数行を書く種目で守る）:
- 親の箇条書き = ノート自身の主張、タブ1つ下げた子 = 文献の引用[[リンク]]や帰結
- リンク先を読めば分かる定義・手順・列挙は再掲しない。埋めるのは「その文献が主張にどう効くか」
- 同じ文献箇所を複数のノートで繰り返し引用しない
- 未決のことは断定せず「未定。候補は◯◯」と書く
"""

import json
import re
import sys
import sqlite3
from datetime import date
from pathlib import Path

from . import lint, permlink, rules

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

RULE_ENTRY = """
## 提案{n}: {heading}

- 対象: `{target}`{state}
- 種目: {kind}（規則ベース・機械が決めたのは条件の充足だけ）

**いまの本文**

{body_block}

**提案**{how}

<!-- after: {pid} -->
{after_block}

**根拠**

- {rationale}

<!-- id: {pid} -->
- [ ] 採用
- [ ] 却下
"""

RULE_NOTE_ENTRY = """
## 提案{n}: [[{name}]] を起票する

- 対象: `{target}`（まだ存在しないノート）
- 種目: 起票待ちキュー（規則ベース）
- 参照元: {refs}

**提案**（このまま新規ノートとして作る。中身は書き換えてよい）

<!-- after: {pid} -->
{after_block}

**根拠**

- {rationale}

<!-- id: {pid} -->
- [ ] 採用
- [ ] 却下
"""

PERM_ENTRY = """
## 提案{n}: [[{ztitle}]] ← [[{link}]]

- 対象: `{target}`（status: {status}・最終編集 {modified}・{days}日放置）
- 種目: Zettel 間リンク（構造と語彙だけで出した候補・スコア {score}）

**いまの本文**

{body_block}

**提案**（この1行を足す。文言はこのブロックを直接書き換えてよい）

<!-- after: {pid} -->
{after_block}

**根拠**

- {rationale}
- つながりは無向なので、[[{link}]] の側に書くほうが自然なら、この提案は却下してそちらへ足してよい。

<!-- id: {pid} -->
- [ ] 採用
- [ ] 却下
"""

FLAG_ENTRY = """
## 提案{n}: {heading}

- 対象: `{target}`
- 種目: {kind}（指摘のみ・機械では直せない）

**いまの frontmatter**

{body_block}

**提案**（正しい値をこのブロックに書いてから採用する）

<!-- after: {pid} -->
{after_block}

**根拠**

- {rationale}

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
    n = by_path.get(p["target"]) or {}
    mod = n.get("modified") or date.fromtimestamp(n.get("mtime", 0)) if n else None
    days = (today - mod).days if mod else 0
    return (STATUS_PRIORITY.get(n.get("status", ""), 1), -days)


def _relation(after: str) -> str:
    m = re.search(r"（([^（）]*)）\s*$", after)
    return m.group(1) if m else "関連"


KIND_LABEL = {"lit_link": "文献リンク", "perm_link": "Zettel 間リンク", "status": "成熟度",
              "tag": "タグ", "queue": "起票待ちキュー", "moc": "MOC収録"}


def _render_lit_link(i: int, p: dict, by_path: dict, today: date) -> str:
    n = by_path[p["target"]]
    lit = by_path[p["source_refs"][0]]
    mod = n["modified"] or date.fromtimestamp(n["mtime"])
    return ENTRY.format(
        n=i, ztitle=n["title"], link=lit["title"], target=p["target"],
        status=n["status"] or "（欠落）", modified=mod.isoformat(), days=(today - mod).days,
        conf=p.get("confidence", "?"), relation=_relation(p["after"]),
        lit_path=p["source_refs"][0],
        body_block=fence(n["body"].strip()), after_block=fence(p["after"]), pid=p["id"],
        rationale=p["rationale"], ev_z=p.get("evidence_zettel", ""),
        ev_l=p.get("evidence_lit", ""))


def _render_perm_link(i: int, p: dict, by_path: dict, today: date) -> str:
    n = by_path[p["target"]]
    dst = by_path[p["source_refs"][0]]
    mod = n["modified"] or date.fromtimestamp(n["mtime"])
    return PERM_ENTRY.format(
        n=i, ztitle=n["title"], link=dst["title"], target=p["target"],
        status=n["status"] or "（欠落）", modified=mod.isoformat(), days=(today - mod).days,
        score=p.get("score", "?"), body_block=fence(n["body"].strip()),
        after_block=fence(p["after"]), pid=p["id"], rationale=p["rationale"])


def _render_rule(i: int, p: dict, by_path: dict) -> str:
    meta = p.get("meta", {})
    if p["type"] == "queue":
        return RULE_NOTE_ENTRY.format(
            n=i, name=meta.get("name", Path(p["target"]).stem), target=p["target"],
            refs="、".join(f"`{s}`" for s in meta.get("referenced_by", [])),
            after_block=fence(p["after"]), pid=p["id"], rationale=p["rationale"])

    n = by_path[p["target"]]
    if p["type"] == "moc":
        z = Path(meta.get("zettel", "")).stem
        return RULE_ENTRY.format(
            n=i, heading=f"[[{n['title']}]] に [[{z}]] を収録する", target=p["target"],
            state=f"（節「{meta.get('section')}」・タグ {meta.get('tag')}）",
            kind=KIND_LABEL["moc"],
            how="（この節見出しの直後に1行足す。節が違うならブロックごと書き換えてよい）",
            body_block=fence(p["before"] or ""), after_block=fence(p["after"]),
            pid=p["id"], rationale=p["rationale"])

    if p["type"] == "status":
        heading = f"[[{n['title']}]] の成熟度を {meta.get('from')} → {meta.get('to')}"
        return RULE_ENTRY.format(
            n=i, heading=heading, target=p["target"],
            state=f"（発リンク{meta.get('out')}・被リンク{meta.get('in')}）",
            kind=KIND_LABEL["status"], how="（frontmatter のこの1行を書き換える）",
            body_block=fence(n["body"].strip()), after_block=fence(p["after"]),
            pid=p["id"], rationale=p["rationale"])

    if p.get("after") is None:  # タグの指摘のみ（機械では直せない）
        return FLAG_ENTRY.format(
            n=i, heading=f"[[{n['title']}]] の {meta.get('kind')}", target=p["target"],
            kind=KIND_LABEL["tag"], body_block=fence(n["fm"].strip()),
            after_block=fence("（ここに正しい frontmatter の行を書く）"),
            pid=p["id"], rationale=p["rationale"])

    return RULE_ENTRY.format(
        n=i, heading=f"[[{n['title']}]] のタグ表記を揃える", target=p["target"], state="",
        kind=KIND_LABEL["tag"], how="（frontmatter のこの1行を書き換える）",
        body_block=fence(n["fm"].strip()), after_block=fence(p["after"]),
        pid=p["id"], rationale=p["rationale"])


def render(cfg: dict, picked: list[dict], notes: list[dict], sheet_name: str, today: date) -> str:
    by_path = {n["path"]: n for n in notes}
    kinds = "・".join(dict.fromkeys(KIND_LABEL.get(p["type"], p["type"]) for p in picked))
    parts = [HEADER.format(today=today.isoformat(), n=len(picked),
                           kinds=kinds, sheet_name=sheet_name)]
    for i, p in enumerate(picked, 1):
        if p["type"] == "lit_link":
            parts.append(_render_lit_link(i, p, by_path, today))
        elif p["type"] == "perm_link":
            parts.append(_render_perm_link(i, p, by_path, today))
        else:
            parts.append(_render_rule(i, p, by_path))
    parts.append("\n---\n\n判定を書き終えたら回収コマンドを実行する。"
                 "チェックが両方空の提案は保留として `data/proposals.jsonl` に残り、次回のシートに再掲される。\n")
    return "".join(parts)


def _linked(a: str, b: str, by_path: dict, idx: dict[str, list[str]]) -> bool:
    """a → b のリンクが既に本文にあるか（人手で貼られていたら提案は用済み）。"""
    body = by_path[a]["body"]
    return any(lint.resolve(name, idx) == b for name in lint.wikilinks(body))


def _alive(p: dict, by_path: dict, decided: set, done: set, idx: dict[str, list[str]]) -> bool:
    """まだシートに載せる資格がある提案か（採否済み・対象消滅を落とす）。"""
    if p["id"] in done:
        return False
    if p["type"] == "queue":
        return p["target"] not in by_path  # 既に起票されたら用済み
    if p["target"] not in by_path:
        return False
    if p["type"] in ("lit_link", "perm_link"):
        refs = p.get("source_refs") or []
        if not refs or refs[0] not in by_path:
            return False
        if p["type"] == "lit_link":
            return (p["target"], refs[0]) not in decided
        # Zettel 間は無向。向きが逆の採否も、人手で貼られたリンクも同じ組として外す
        if (p["target"], refs[0]) in decided or (refs[0], p["target"]) in decided:
            return False
        return not (_linked(p["target"], refs[0], by_path, idx)
                    or _linked(refs[0], p["target"], by_path, idx))
    return True


def run(cfg: dict, findings_path: Path | None, out: Path | None) -> None:
    root: Path = cfg["_root"]
    src = findings_path or (root / "data" / "findings.json")
    min_conf = cfg.get("report", {}).get("min_confidence", 5)
    links: list[dict] = []
    if src.exists():
        findings = json.loads(src.read_text(encoding="utf-8"))
        links = [f for f in findings
                 if f.get("verdict") == "link" and f.get("confidence", 0) >= min_conf]
        links.sort(key=lambda f: (-f.get("confidence", 0), -f.get("score", 0)))
    elif findings_path is not None:
        sys.exit(f"findings が見つからない: {src}")
    else:
        print(f"findings なし（{src}）。規則ベースの提案だけでシートを作る")

    notes = lint.load_notes(cfg)
    res = lint.analyze(cfg, notes)
    existing, fresh = build_proposals(cfg, links, notes)
    fresh += rules.build(cfg, notes, res)
    fresh += permlink.build(cfg, notes, decided_pairs(root))
    if fresh:
        with (root / "data" / "proposals.jsonl").open("a", encoding="utf-8") as fp:
            for p in fresh:
                fp.write(json.dumps(p, ensure_ascii=False) + "\n")

    # 保留（未採否）の既存提案を先に、今回の新規を後に。target が Vault から消えたものは落とす
    by_path = {n["path"]: n for n in notes}
    idx = lint.title_index(notes)
    done, decided = decided_ids(root), decided_pairs(root)
    pending = [p for p in existing + fresh if _alive(p, by_path, decided, done, idx)]
    # 規則ベースの提案は作った週の実測値を抱えている。返ってくる週には vault が動いているので
    # 現在の数字へ採り直し、条件が消えたものはシートから外す（凍結した数字で判断させない）
    pending, obsolete = rules.refresh(pending, rules.current(cfg, notes, res))
    if obsolete:
        print(f"条件が消えた提案 {len(obsolete)} 件をシートから外した"
              f"（{'、'.join(p['id'] for p in obsolete[:5])}{' ほか' if len(obsolete) > 5 else ''}）")
    today = date.today()
    pending.sort(key=lambda p: order_key(p, by_path, today))
    cap = cfg.get("sheet", {}).get("max_proposals", 5)
    # 種目の偏りを防ぐ: 規則ベースに枠を確保してから残りを埋める（どちらも足りなければ融通する）
    quota = min(cfg.get("rules", {}).get("sheet_quota", 2), cap)
    perm_quota = min(cfg.get("permlink", {}).get("sheet_quota", 1), max(0, cap - quota))
    rule_side = [p for p in pending if p["type"] not in ("lit_link", "perm_link")]
    perm_side = [p for p in pending if p["type"] == "perm_link"]
    link_side = [p for p in pending if p["type"] == "lit_link"]
    picked = (rule_side[:quota] + perm_side[:perm_quota]
              + link_side[:max(0, cap - quota - perm_quota)])
    if len(picked) < cap:
        rest = [p for p in pending if p not in picked]
        picked += rest[:cap - len(picked)]
    picked.sort(key=lambda p: order_key(p, by_path, today))
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
