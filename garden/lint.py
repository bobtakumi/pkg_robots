"""garden lint — 機械照合と庭の健康診断（拡張プラン R2）。

Vault を読み取り専用で走査し、決定的なコードだけで次を報告する（LLM 不使用）:
  ① wikilink の解決 — 未解決は不具合ではなく「起票待ちキュー」として別枠表示（2026-08-02 確定の運用）
  ② タグ統制語彙（07「成熟度とタグの運用基準」15種）への適合と表記の乱れ
  ③ 成熟度とリンク実測の整合 — 昇格/降格の**候補検出のみ**（自動変更はしない）
  ④ --proposals: proposals.jsonl の適用前提チェック（target 実在・before 一字一致・after のリンク解決）

Vault へは一切書き込まない。ノートの読み込みは sheet.py からも使う（この repo で
vault を読む唯一の共通入口）。
"""

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from .index import INLINE_TAG_RE, WIKILINK_RE, split_frontmatter

# frontmatter のタグ行（リスト形式）。表記の乱れを見たいので引用符・# は剥がさず捕まえる
FM_TAG_ITEM_RE = re.compile(r"^\s*-\s*(.+?)\s*$")
ATTACHMENT_RE = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|pdf|epub|excalidraw|canvas|base|mp4|webm|mov)$", re.I)
STATUS_RE = re.compile(r"^status\s*:\s*(.*)$", re.M)
MODIFIED_RE = re.compile(r"^modified\s*:\s*(.*)$", re.M)

# 07 の成熟度条件のうち、リンク実測だけで判定できる部分。
# Seeding は「リンクが1本以上」＝発・被のどちらでもよい（Inbox の条件が「1本もない」なので）。
# Budding は「発リンク2本以上」。本文要素2つ以上の条件は機械では見られないので候補止まり。
MIN_DEGREE_SEEDING = 1
MIN_OUTLINKS_BUDDING = 2
EXEMPT_STATUS = {"Evergreen", "Open"}  # Evergreen は暫定措置で人間判断・Open は育ち具合を問わない


def parse_fm_tags(fm: str) -> tuple[list[str], bool]:
    """frontmatter の tags を生のトークンで返す。(tokens, tags キーがあるか)。"""
    tokens: list[str] = []
    found, in_tags = False, False
    for line in fm.splitlines():
        if re.match(r"^tags\s*:", line):
            found, in_tags = True, True
            rest = line.split(":", 1)[1].strip()
            if rest.startswith("["):
                tokens += [t.strip() for t in rest.strip("[]").split(",") if t.strip()]
                in_tags = False
            continue
        if in_tags:
            m = FM_TAG_ITEM_RE.match(line)
            if m:
                tokens.append(m.group(1))
            elif line.strip():
                in_tags = False
    return tokens, found


def _to_date(s: str) -> date | None:
    s = s.strip().strip("\"'")[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def load_notes(cfg: dict) -> list[dict]:
    """Vault の .md を config の exclude を尊重して読む（読み取り専用）。"""
    vault = Path(cfg["vault"]["path"])
    prefixes = tuple(cfg["vault"]["exclude_prefixes"])
    fragments = cfg["vault"]["exclude_fragments"]
    notes = []
    for p in sorted(vault.rglob("*.md")):
        rel = p.relative_to(vault).as_posix()
        if rel.startswith(prefixes) or any(f in f"/{rel}" for f in fragments):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm, body = split_frontmatter(text)
        tokens, has_tags = parse_fm_tags(fm)
        m_st, m_mod = STATUS_RE.search(fm), MODIFIED_RE.search(fm)
        notes.append({
            "path": rel, "title": p.stem, "fm": fm, "body": body,
            "tag_tokens": tokens, "has_tags_key": has_tags,
            "status": (m_st.group(1).strip().strip("\"'") if m_st else ""),
            "has_status_key": m_st is not None,
            "modified": _to_date(m_mod.group(1)) if m_mod else None,
            "mtime": p.stat().st_mtime,
        })
    return notes


def title_index(notes: list[dict]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for n in notes:
        idx.setdefault(n["title"], []).append(n["path"])
    return idx


def wikilinks(body: str) -> list[str]:
    """本文中の wikilink のリンク先名（`|alias` と `#見出し` を落とし、パス指定は basename 化）。

    添付の埋め込み（`![[Pasted image ….png]]`）は除く。Assets は索引対象外なので
    未解決に数えると起票待ちキューが画像で埋まる。
    """
    names = []
    for m in WIKILINK_RE.finditer(body):
        if m.start() > 0 and body[m.start() - 1] == "!":
            continue
        name = m.group(1).strip().split("/")[-1].rstrip("\\").strip()
        if ATTACHMENT_RE.search(name):
            continue
        names.append(name)
    return names


def resolve(name: str, idx: dict[str, list[str]]) -> str | None:
    paths = idx.get(name)
    return paths[0] if paths else None


def analyze(cfg: dict, notes: list[dict]) -> dict:
    idx = title_index(notes)
    scope = tuple(cfg.get("lint", {}).get("link_scope", ["2_Permanent/", "1_Literature/"]))
    allowed = set(cfg.get("lint", {}).get("allowed_tags", []))

    # ① リンク解決
    queue, ambiguous = [], []
    out_deg: dict[str, int] = {}
    in_deg: dict[str, int] = {}
    for n in notes:
        if not n["path"].startswith(scope):
            continue
        for name in wikilinks(n["body"]):
            target = resolve(name, idx)
            if target is None:
                queue.append({"src": n["path"], "name": name,
                              "tree": n["path"].split("/")[0]})
                continue
            out_deg[n["path"]] = out_deg.get(n["path"], 0) + 1
            in_deg[target] = in_deg.get(target, 0) + 1
            if len(idx[name]) > 1:
                ambiguous.append({"src": n["path"], "name": name, "candidates": idx[name]})

    # ② タグ
    tag_issues = []
    for n in notes:
        if not n["path"].startswith("2_Permanent/"):
            continue
        clean = []
        for t in n["tag_tokens"]:
            if t != t.strip("\"'") or t.startswith("#"):
                tag_issues.append({"path": n["path"], "kind": "表記", "detail": t})
            clean.append(t.strip("\"'").lstrip("#"))
        for t in clean:
            if allowed and t not in allowed:
                tag_issues.append({"path": n["path"], "kind": "語彙外", "detail": t})
        if not n["has_tags_key"]:
            tag_issues.append({"path": n["path"], "kind": "tagsキー欠落", "detail": ""})
        elif not clean:
            tag_issues.append({"path": n["path"], "kind": "tags空", "detail": ""})
        # status は Zettel の成熟度なので Zettelkasten 配下のみ必須（MOC には付けない運用）
        if not n["has_status_key"] and n["path"].startswith("2_Permanent/Zettelkasten/"):
            tag_issues.append({"path": n["path"], "kind": "statusキー欠落", "detail": ""})
        for t in set(INLINE_TAG_RE.findall(n["body"])):
            tag_issues.append({"path": n["path"], "kind": "インラインタグ", "detail": t})

    # ③ 成熟度とリンク実測（候補検出のみ）
    zettels = [n for n in notes if n["path"].startswith("2_Permanent/Zettelkasten/")]
    promote, demote, isolated = [], [], []
    for n in zettels:
        o, i = out_deg.get(n["path"], 0), in_deg.get(n["path"], 0)
        st = n["status"]
        if o == 0 and i == 0:
            isolated.append({"path": n["path"], "kind": "完全孤立", "status": st})
        elif o == 0:
            isolated.append({"path": n["path"], "kind": "発リンク0", "status": st})
        elif i == 0:
            isolated.append({"path": n["path"], "kind": "被リンク0", "status": st})
        if st in EXEMPT_STATUS:
            continue
        if st == "Inbox" and o + i >= MIN_DEGREE_SEEDING:
            promote.append({"path": n["path"], "from": st, "to": "Seeding", "out": o, "in": i})
        elif st == "Seeding" and o >= MIN_OUTLINKS_BUDDING:
            promote.append({"path": n["path"], "from": st, "to": "Budding", "out": o, "in": i})
        elif st == "Seeding" and o + i < MIN_DEGREE_SEEDING:
            demote.append({"path": n["path"], "from": st, "to": "Inbox", "out": o, "in": i})
        elif st == "Budding" and o < MIN_OUTLINKS_BUDDING:
            demote.append({"path": n["path"], "from": st, "to": "Seeding", "out": o, "in": i})

    dup = {t: ps for t, ps in idx.items() if len(ps) > 1}
    return {
        "notes": len(notes), "zettels": len(zettels),
        "queue": queue, "ambiguous": ambiguous, "duplicate_basenames": dup,
        "tag_issues": tag_issues, "promote": promote, "demote": demote,
        "isolated": isolated,
        "status_hist": _hist(n["status"] or "（欠落）" for n in zettels),
    }


def _hist(values) -> dict[str, int]:
    h: dict[str, int] = {}
    for v in values:
        h[v] = h.get(v, 0) + 1
    return dict(sorted(h.items(), key=lambda kv: -kv[1]))


def check_proposals(cfg: dict, notes: list[dict]) -> list[dict]:
    """proposals.jsonl の適用前提チェック（apply の前段を兼ねる）。"""
    root: Path = cfg["_root"]
    f = root / "data" / "proposals.jsonl"
    if not f.exists():
        return []
    idx = title_index(notes)
    by_path = {n["path"]: n for n in notes}
    problems = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        p = json.loads(line)
        note = by_path.get(p["target"])
        if p.get("type") == "queue":
            # 起票提案は「まだ無いノート」を作る。既にあるなら用済み（提案が古い）
            if note is not None:
                problems.append({"id": p["id"], "kind": "起票済み", "detail": p["target"]})
            continue
        if note is None:
            problems.append({"id": p["id"], "kind": "target不在", "detail": p["target"]})
            continue
        haystack = note["fm"] if p.get("type") in ("status", "tag") else note["body"]
        if p.get("before") and p["before"].rstrip("\n") not in haystack:
            problems.append({"id": p["id"], "kind": "before不一致", "detail": p["before"][:60]})
        for name in wikilinks(p.get("after") or ""):
            if resolve(name, idx) is None:
                problems.append({"id": p["id"], "kind": "afterのリンク未解決", "detail": name})
    return problems


def run(cfg: dict, as_json: bool, with_proposals: bool) -> None:
    notes = load_notes(cfg)
    res = analyze(cfg, notes)
    if with_proposals:
        res["proposal_problems"] = check_proposals(cfg, notes)
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        return

    print(f"== garden lint == 走査 {res['notes']} ノート（うち zettel {res['zettels']}）")
    perm = [q for q in res["queue"] if q["tree"] == "2_Permanent"]
    other = [q for q in res["queue"] if q["tree"] != "2_Permanent"]
    print(f"\n[起票待ちキュー] 2_Permanent {len(perm)} 件"
          f"（未解決リンク＝意図的な運用。エラーではない）")
    for q in perm:
        print(f"  - [[{q['name']}]] ← {q['src']}")
    print(f"  ほか 1_Literature 側の未解決 {len(other)} 件（多くは Archive の旧ノート・節見出しへの参照）")
    for q in other[:10]:
        print(f"    - [[{q['name']}]] ← {q['src']}")
    if len(other) > 10:
        print(f"    …ほか {len(other) - 10} 件（全件は --json）")
    print(f"\n[同名 basename] 重複 {len(res['duplicate_basenames'])} 種 / "
          f"うちリンクで参照され曖昧なもの {len(res['ambiguous'])} 件")
    for a in res["ambiguous"][:10]:
        print(f"  ! [[{a['name']}]]（{a['src']}）→ {len(a['candidates'])} 候補: {a['candidates']}")
    if len(res["ambiguous"]) > 10:
        print(f"    …ほか {len(res['ambiguous']) - 10} 件（全件は --json）")

    print(f"\n[タグ] 違反 {len(res['tag_issues'])} 件")
    for t in res["tag_issues"]:
        print(f"  ! {t['kind']}: {t['detail']} — {t['path']}")

    print(f"\n[成熟度] 現状 {res['status_hist']}")
    print(f"  昇格候補 {len(res['promote'])} 件"
          f"（リンク実測は上位の条件を満たす。Budding は本文要素2つ以上の確認が別途要る＝自動変更しない）")
    for p in res["promote"]:
        print(f"    ↑ {p['from']} → {p['to']}（発{p['out']}・被{p['in']}） {p['path']}")
    print(f"  降格候補 {len(res['demote'])} 件")
    for p in res["demote"]:
        print(f"    ↓ {p['from']} → {p['to']}（発{p['out']}・被{p['in']}） {p['path']}")

    kinds = _hist(i["kind"] for i in res["isolated"])
    print(f"\n[孤立] {len(res['isolated'])} 件 {kinds}")
    for i in res["isolated"]:
        if i["kind"] == "完全孤立":
            print(f"    × {i['kind']}（{i['status']}） {i['path']}")

    if with_proposals:
        probs = res["proposal_problems"]
        print(f"\n[提案の照合] 不整合 {len(probs)} 件")
        for p in probs:
            print(f"  ! {p['id']} {p['kind']}: {p['detail']}")
        if probs:
            sys.exit(1)
