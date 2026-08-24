"""garden permlink — Zettel 間リンクの候補生成（拡張プラン R5）。

既存の `candidates`（層跨ぎ＝Zettel×文献）が埋め込み類似に頼るのに対し、こちらは
**構造と語彙だけ**で候補を出す。埋め込みサーバ（Ollama）が居ない端末でも動くこと、
そして「なぜこの2本か」を人間に説明できることを優先している。

使う手がかりは4つ。いずれも vault を読むだけで決まる。

- 共引用: 同じ文献ノートを引いている2本（読んだものが同じ = 論の材料が同じ）
- 共通タグ: 主題軸のタグが重なる（`source/` は他者由来の印なので数えない）
- 二歩先: 片方の隣接ノートともう片方の隣接ノートが重なる（グラフ上の近さ）
- 語彙: タイトルと本文の語が重なる（IDF 重みつき。日本語なので語の切り出しは文字種の連なりで代用）

スコアは4つの重みつき和。閾値と重みは `[permlink]` で調整できる。判定は人間に返す前提で、
このモジュールは vault へ書き込まない。

候補は `build()` で週次シートの提案（type = `perm_link`）に変換され、文献リンク・規則ベースと
同じ 1 枚に載る。シート内の枠数は `[permlink] sheet_quota`、1 回に作る新規提案の上限は
`max_new` で絞る（少数・非一括の原則）。
"""

import json
import math
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from . import lint

ZETTEL_PREFIX = "2_Permanent/Zettelkasten/"
MOC_PREFIX = "2_Permanent/MOC/"
LIT_PREFIX = "1_Literature/"
# 日本語の語の切り出しは形態素解析なしで済ませる（外部依存を増やさない方針）。
# 2026-08-03 の較正で、漢字・カタカナの連なりを語とする方式（top-10 recall 64%）より
# **文字bigram**（68%・top-30 では 68%→75%）が良かったので後者を採る。活用の揺れや
# 「ホワイトボード」のような複合語の部分一致を拾えるのが効いている。
DROP_RE = re.compile(r"[\s、。「」『』（）()\[\]|#*\-—:：/\\!?！？,.]")
# 重みは 2026-08-03 の較正（大掃除で採用された Zettel 間リンク28本）で決めた。
# 大掃除**前**の庭は文献リンク9本・Zettel 間リンクも疎で、共引用や二歩先がほとんど効かない。
# 疎なグラフでは語彙が主役になるため w_term を最大に置き、構造の手がかりは加点として使う。
DEFAULTS = {"top_k": 10, "min_score": 0.06, "term_floor": 0.02,
            "w_cocite": 0.25, "w_cotag": 0.10, "w_hop": 0.20, "w_term": 0.45,
            "sheet_quota": 1, "max_new": 3}


def opts(cfg: dict) -> dict:
    o = dict(DEFAULTS)
    o.update(cfg.get("permlink", {}) or {})
    return o


def bigrams(text: str) -> list[str]:
    s = DROP_RE.sub("", text)
    return [s[i:i + 2] for i in range(len(s) - 1)]


def tokens(note: dict) -> Counter:
    """タイトルを3倍重みで数えた文字bigram の袋。"""
    c = Counter(bigrams(note["title"]))
    for t in list(c):
        c[t] *= 3
    c.update(bigrams(note["body"]))
    return c


def subject_tags(note: dict) -> set[str]:
    """主題軸と活動軸のタグ。出典軸（source/）は他者由来の印なので類似の根拠にしない。"""
    out = set()
    for t in note["tag_tokens"]:
        t = t.strip("\"'").lstrip("#").strip()
        if t and not t.startswith("source/"):
            out.add(t)
    return out


def build_graph(notes: list[dict]) -> dict:
    """Zettel のリンク構造・タグ・語彙をまとめて作る。"""
    idx = lint.title_index(notes)
    by_path = {n["path"]: n for n in notes}
    zettels = [n for n in notes if n["path"].startswith(ZETTEL_PREFIX)]

    lit_of: dict[str, set[str]] = {}
    nbr: dict[str, set[str]] = defaultdict(set)   # Zettel 間の隣接（無向）
    moc_of: dict[str, set[str]] = defaultdict(set)
    linked: set[tuple[str, str]] = set()          # 既にリンクがある組（無向・正規化）

    for n in notes:
        src = n["path"]
        for name in lint.wikilinks(n["body"]):
            dst = lint.resolve(name, idx)
            if dst is None:
                continue
            if src.startswith(ZETTEL_PREFIX) and dst.startswith(LIT_PREFIX):
                lit_of.setdefault(src, set()).add(dst)
            if src.startswith(MOC_PREFIX) and dst.startswith(ZETTEL_PREFIX):
                moc_of[dst].add(src)
            if src.startswith(ZETTEL_PREFIX) and dst.startswith(ZETTEL_PREFIX):
                nbr[src].add(dst)
                nbr[dst].add(src)
                linked.add(tuple(sorted((src, dst))))

    tok = {n["path"]: tokens(n) for n in zettels}
    df: Counter = Counter()
    for c in tok.values():
        df.update(set(c))
    n_doc = max(1, len(tok))
    idf = {t: math.log(n_doc / (1 + d)) + 1.0 for t, d in df.items()}
    norm = {}
    for p, c in tok.items():
        norm[p] = math.sqrt(sum((v * idf[t]) ** 2 for t, v in c.items())) or 1.0

    return {"zettels": zettels, "by_path": by_path, "lit_of": lit_of, "nbr": nbr,
            "moc_of": moc_of, "linked": linked, "tok": tok, "idf": idf, "norm": norm,
            "tags": {n["path"]: subject_tags(n) for n in zettels}}


def term_sim(g: dict, a: str, b: str) -> float:
    ta, tb = g["tok"][a], g["tok"][b]
    if len(ta) > len(tb):
        ta, tb = tb, ta
    idf = g["idf"]
    dot = sum(v * tb[t] * idf[t] ** 2 for t, v in ta.items() if t in tb)
    return dot / (g["norm"][a] * g["norm"][b])


def score_pairs(g: dict, o: dict, skip: set[tuple[str, str]] | None = None) -> list[dict]:
    """全 Zettel 対を採点する。既にリンクがある組と skip 指定の組は外す。"""
    skip = skip or set()
    paths = [n["path"] for n in g["zettels"]]
    # 素の全対は 118^2 でも軽いが、手がかりが1つも無い対は落として説明可能なものだけ残す
    out = []
    for i, a in enumerate(paths):
        for b in paths[i + 1:]:
            key = (a, b)
            if key in g["linked"] or key in skip:
                continue
            cocite = len(g["lit_of"].get(a, set()) & g["lit_of"].get(b, set()))
            cotag = len(g["tags"][a] & g["tags"][b])
            hop = len(g["nbr"].get(a, set()) & g["nbr"].get(b, set()))
            comoc = len(g["moc_of"].get(a, set()) & g["moc_of"].get(b, set()))
            term = term_sim(g, a, b)
            if not (cocite or hop or comoc or term >= o["term_floor"]):
                # 手がかりが1つも無い組は落とす。語彙だけでも通すのは、大掃除前のように
                # リンクが疎な庭では構造の手がかりがほぼ存在しないため（較正で確認）
                continue
            score = (o["w_cocite"] * min(1.0, cocite / 2)
                     + o["w_cotag"] * min(1.0, (cotag + comoc) / 2)
                     + o["w_hop"] * min(1.0, hop / 3)
                     + o["w_term"] * min(1.0, term * 3))
            if score < o["min_score"]:
                continue
            out.append({"a": a, "b": b, "score": round(score, 4),
                        "cocite": cocite, "cotag": cotag, "hop": hop, "comoc": comoc,
                        "term": round(term, 4)})
    out.sort(key=lambda r: -r["score"])
    return out


def top_per_note(pairs: list[dict], k: int) -> dict[str, list[dict]]:
    per: dict[str, list[dict]] = defaultdict(list)
    for r in pairs:
        for src, dst in ((r["a"], r["b"]), (r["b"], r["a"])):
            if len(per[src]) < k:
                per[src].append({**r, "src": src, "dst": dst})
    return per


def reason(g: dict, r: dict) -> str:
    bits = []
    if r["cocite"]:
        shared = sorted(g["lit_of"].get(r["a"], set()) & g["lit_of"].get(r["b"], set()))
        names = "、".join(f"[[{Path(s).stem}]]" for s in shared[:2])
        bits.append(f"同じ文献を引いている（{names}）")
    if r["hop"]:
        common = sorted(g["nbr"].get(r["a"], set()) & g["nbr"].get(r["b"], set()))
        names = "、".join(f"[[{Path(s).stem}]]" for s in common[:2])
        bits.append(f"共通の隣接ノートが{r['hop']}本（{names}）")
    if r["comoc"]:
        bits.append("同じ MOC に載っている")
    if r["cotag"]:
        bits.append(f"主題タグが{r['cotag']}本重なる")
    if r["term"] >= 0.1:
        bits.append(f"語彙の重なり {r['term']:.2f}")
    return "、".join(bits) or "手がかり弱め"


def snapshot(cfg: dict, ref: str) -> Path:
    """vault を指定コミット時点で取り出す（較正用。現在の vault は変更しない）。"""
    vault = cfg["vault"]["path"]
    tmp = Path(tempfile.mkdtemp(prefix="garden-snap-"))
    proc = subprocess.run(["git", "-C", vault, "archive", ref, "2_Permanent", "1_Literature"],
                          capture_output=True)
    if proc.returncode != 0:
        sys.exit(f"スナップショットを取れない（{ref}）: {proc.stderr.decode()[:200]}")
    subprocess.run(["tar", "-x", "-C", str(tmp)], input=proc.stdout, check=True)
    return tmp


def load(cfg: dict, ref: str | None) -> list[dict]:
    if ref is None:
        return lint.load_notes(cfg)
    root = snapshot(cfg, ref)
    return lint.load_notes({**cfg, "vault": {**cfg["vault"], "path": str(root)}})


def evaluate(g: dict, o: dict, gold_path: Path) -> None:
    """大掃除で人間が採用した Zettel 間リンクを、どれだけ候補に出せるかを測る。"""
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    pairs = [p for p in gold["pairs"] if p["human"] == "accepted"]
    # 正解のリンクは適用済みで vault に実在する。較正では「まだ無い」ものとして扱う
    skip_off = {tuple(sorted((p["source_path"], t["path"]))) for p in pairs for t in p["targets"]}
    g["linked"] -= skip_off
    scored = score_pairs(g, o)

    for k in (5, 10, 30):
        per = top_per_note(scored, k)
        hit = miss = absent = 0
        misses = []
        for p in pairs:
            src = p["source_path"]
            if src not in g["by_path"]:
                absent += 1
                continue
            cands = {r["dst"] for r in per.get(src, [])}
            if any(t["path"] in cands for t in p["targets"]):
                hit += 1
            else:
                miss += 1
                misses.append(p)
        n = hit + miss
        print(f"  top-{k:>2} recall = {hit}/{n} = {hit / n:.1%}" if n else "  評価対象なし")
        if k == 10:
            for p in misses:
                print(f"      miss: {p['source_title']} → "
                      f"{'、'.join(t['title'] for t in p['targets'])}")
    if absent:
        print(f"  （スナップショットに無い正解 {absent} 件は対象外）")


STATUS_PRIORITY = {"Inbox": 0, "Seeding": 0}  # 7/11 設計: Inbox / Seeding を優先


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _side_key(note: dict, today: date) -> tuple[int, int]:
    """提案を載せる側を選ぶ順序。Inbox / Seeding が先、次に放置が長い方。"""
    mod = note.get("modified") or date.fromtimestamp(note["mtime"])
    return (STATUS_PRIORITY.get(note.get("status", ""), 1), -(today - mod).days)


def build(cfg: dict, notes: list[dict], decided: set[tuple[str, str]]) -> list[dict]:
    """候補ペアを週次シートの提案へ変換する（proposals.jsonl へは書かない）。

    リンクは無向なので、どちらのノートに 1 行足しても庭のつながりは同じ。手を入れる側は
    週次の優先順（Inbox / Seeding 優先・放置が長い順）に合わせて選ぶ。`decided` は採否が
    付いた組で、向きが逆でも同じ組とみなして外す。
    """
    root: Path = cfg["_root"]
    o = opts(cfg)
    existing = _load_jsonl(root / "data" / "proposals.jsonl")
    seen = {tuple(sorted((p["target"], p["source_refs"][0])))
            for p in existing
            if p.get("type") == "perm_link" and p.get("source_refs")}
    seen |= {tuple(sorted(pair)) for pair in decided}

    g = build_graph(notes)
    today = date.today()
    batch = today.strftime("%Y%m%d")
    seq = 0
    for p in existing:
        m = re.match(rf"p-{batch}-(\d+)$", p["id"])
        if m:
            seq = max(seq, int(m.group(1)))

    fresh: list[dict] = []
    for r in score_pairs(g, o):
        if len(fresh) >= o["max_new"]:
            break
        key = tuple(sorted((r["a"], r["b"])))
        if key in seen:
            continue
        src, dst = sorted((g["by_path"][r["a"]], g["by_path"][r["b"]]),
                          key=lambda n: _side_key(n, today))
        seen.add(key)
        seq += 1
        fresh.append({
            "id": f"p-{batch}-{seq:03d}",
            "type": "perm_link",
            "target": src["path"],
            "before": None,
            "after": f"- [[{dst['title']}]]（関連）",
            "rationale": reason(g, r),
            "source_refs": [dst["path"]],
            "batch": batch,
            "proposer": "permlink",
            "score": r["score"],
            "meta": {k: r[k] for k in ("cocite", "cotag", "hop", "comoc", "term")},
        })
    return fresh


def run(cfg: dict, ref: str | None, do_eval: bool, as_json: bool) -> None:
    o = opts(cfg)
    notes = load(cfg, ref)
    g = build_graph(notes)
    print(f"== garden permlink == Zettel {len(g['zettels'])} 本"
          f"（{'現在の vault' if ref is None else f'スナップショット {ref}'}）")

    if do_eval:
        gold = cfg["_root"] / "eval" / "permlink_gold_20260803.json"
        if not gold.exists():
            sys.exit(f"正解データが無い: {gold}（eval/build_permlink_gold.py で作る）")
        print(f"\n== 較正（大掃除で採用された Zettel 間リンク）==")
        evaluate(g, o, gold)
        return

    pairs = score_pairs(g, o)
    per = top_per_note(pairs, o["top_k"])
    if as_json:
        print(json.dumps(pairs[:200], ensure_ascii=False, indent=1))
        return
    print(f"候補 {len(pairs)} 組（min_score={o['min_score']}・上位を対象ノート別に {o['top_k']} 本まで）\n")
    for r in pairs[:20]:
        a, b = g["by_path"][r["a"]]["title"], g["by_path"][r["b"]]["title"]
        print(f"  {r['score']:.3f}  [[{a}]] ⇄ [[{b}]]")
        print(f"          {reason(g, r)}")
    if len(pairs) > 20:
        print(f"\n  …ほか {len(pairs) - 20} 組（全件は --json）")
    print("\n（この一覧は確認用。実際にシートへ載せるのは garden sheet。判断は必ず人間に返す）")
