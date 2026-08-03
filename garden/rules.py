"""garden rules — 規則ベースの提案生成（拡張プラン R4）。

`lint` が決定的に検出したもの（成熟度の昇降格候補・タグ表記の乱れ・起票待ちキュー）を
週次シートに載る「提案」へ変換する。LLM は使わない。判断は必ず人間に返す。

方針（2026-08-02 の運用確定と 2026-08-03 のバッチ2 返却から）:
- 昇格はリンク実測だけで機械判定できる。07 基準の「本文要素2つ以上」は見られないので、
  提案文で人間に確認を促し、自動では変えない
- 未解決リンクは欠陥ではなく**意図的な起票待ちキュー**。既定の後始末は削除ではなく起票で、
  「キューに残す」も正当な回答。だから却下を選びやすい文面にする
- 語彙外タグ・tags/status キーの欠落は機械では直せない（何を入れるかが判断）。
  表記の乱れ（引用符・先頭 `#`）だけを機械修正の提案にし、残りは指摘として同じシートに出す
"""

import json
import re
from datetime import date
from pathlib import Path

from . import lint

NEW_NOTE_TEMPLATE = """---
created: {today}
modified: {today}
tags:
  - {tag}
status: Inbox
---
- （{name} について書く。タイトルが主張になっているか確認する）
"""


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _next_seq(existing: list[dict], batch: str) -> int:
    n = 0
    for p in existing:
        m = re.match(rf"p-{batch}-(\d+)$", p["id"])
        if m:
            n = max(n, int(m.group(1)))
    return n + 1


def _status_line(status: str) -> str:
    return f"status: {status}"


def _first_tag(note: dict) -> str:
    for t in note["tag_tokens"]:
        t = t.strip("\"'").lstrip("#")
        if t:
            return t
    return "Inbox"


def current(cfg: dict, notes: list[dict], res: dict) -> dict[str, dict]:
    """いまの vault から導ける規則ベース提案を rule_key → 中身 で返す（重複抑止をかけない生の集合）。

    `build` はここから未提案のものだけを拾い、`refresh` は保留中の提案の実測値を
    ここで採り直す。提案を作った週と人間が返す週がずれても、シートには常に現在の数字が載る。
    """
    by_path = {n["path"]: n for n in notes}
    today = date.today().isoformat()
    quotas = cfg.get("rules", {})
    out: dict[str, dict] = {}

    def emit(rule_key: str, **fields) -> None:
        out.setdefault(rule_key, fields)

    # ① 成熟度（昇格・降格）
    for kind, rows in (("promote", res["promote"]), ("demote", res["demote"])):
        for r in rows[:quotas.get("max_status", 20)]:
            note = by_path.get(r["path"])
            if note is None:
                continue
            arrow = "昇格" if kind == "promote" else "降格"
            extra = ("Budding は 07 基準で「本文に参照でない自分の推論・根拠・具体例・条件が2要素以上」"
                     "も要る。リンク数の条件だけは満たしたので、本文側を見て判断してほしい"
                     if r["to"] == "Budding" else
                     "リンク実測が現在の成熟度の条件を下回っている")
            emit(f"status:{r['path']}:{r['from']}->{r['to']}",
                 type="status", target=r["path"],
                 before=_status_line(r["from"]), after=_status_line(r["to"]),
                 rationale=f"発リンク{r['out']}・被リンク{r['in']}。{extra}",
                 meta={"kind": arrow, "from": r["from"], "to": r["to"],
                       "out": r["out"], "in": r["in"]})

    # ② タグ表記の乱れ（引用符・先頭 #）は機械修正できる。ほかは指摘として出す
    for t in res["tag_issues"][:quotas.get("max_tag", 20)]:
        note = by_path.get(t["path"])
        if note is None:
            continue
        if t["kind"] == "表記":
            raw, clean = t["detail"], t["detail"].strip("\"'").lstrip("#")
            emit(f"tag:{t['path']}:{raw}",
                 type="tag", target=t["path"],
                 before=f"  - {raw}", after=f"  - {clean}",
                 rationale="タグの表記ゆれ。引用符と先頭の # を落として統制語彙の書き方に揃える",
                 meta={"kind": t["kind"]})
        else:
            emit(f"tag:{t['path']}:{t['kind']}:{t['detail']}",
                 type="tag", target=t["path"], before=None, after=None,
                 rationale=f"{t['kind']}: {t['detail'] or '（値なし）'}。"
                           "何を入れるかは判断が要るので、機械では直さない。"
                           "採用ならこの場で正しい値を書き足してほしい",
                 meta={"kind": t["kind"], "detail": t["detail"]})

    # ③ 起票待ちキュー（2_Permanent 側の未解決リンクのみ）
    queue = [q for q in res["queue"] if q["tree"] == "2_Permanent"]
    seen: dict[str, list[str]] = {}
    for q in queue:
        seen.setdefault(q["name"], []).append(q["src"])
    for name, srcs in list(seen.items())[:quotas.get("max_queue", 10)]:
        src = by_path.get(srcs[0])
        target = f"2_Permanent/Zettelkasten/{name}.md"
        emit(f"queue:{name}",
             type="queue", target=target, before=None,
             after=NEW_NOTE_TEMPLATE.format(today=today, name=name,
                                            tag=_first_tag(src) if src else "Inbox"),
             rationale=f"{len(srcs)}本のノートから参照されているが実体がない。"
                       "未解決リンクは欠陥ではなく起票待ちのキューなので、既定の後始末は起票。"
                       "まだ書くものがなければ却下でよい（キューに残る）",
             meta={"kind": "new_note", "name": name, "referenced_by": srcs})

    return out


def build(cfg: dict, notes: list[dict], res: dict) -> list[dict]:
    """lint の結果から未提案・未決の rules 提案を作る（proposals.jsonl へは書かない）。"""
    root: Path = cfg["_root"]
    existing = load_jsonl(root / "data" / "proposals.jsonl")
    # 同じ指摘を毎週出さないための鍵。採否が付いた提案の鍵も含める
    known = {p.get("rule_key") for p in existing if p.get("rule_key")}
    batch = date.today().strftime("%Y%m%d")
    seq = _next_seq(existing, batch)

    fresh: list[dict] = []
    for rule_key, fields in current(cfg, notes, res).items():
        if rule_key in known:
            continue
        fresh.append({
            "id": f"p-{batch}-{seq:03d}", "batch": batch, "proposer": "rules",
            "rule_key": rule_key, "source_refs": [], **fields,
        })
        seq += 1
    return fresh


def refresh(pending: list[dict], live: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """保留中の規則ベース提案を現在の実測値へ更新し、条件を満たさなくなったものを落とす。

    提案を作った週と人間が返す週の間に vault は動く。凍結した数字のまま見せると、
    「発リンク4・被リンク1」と書いてあるのに実際は被リンク2、という食い違いが起きる
    （2026-08-03 の通し検証で実際に発生）。判断材料は常に現在の実測でなければならない。

    戻り値は (載せてよい提案, 条件が消えた提案)。後者はシートから外す。
    """
    alive, obsolete = [], []
    for p in pending:
        key = p.get("rule_key")
        if not key:  # rules 由来でない（文献リンク等）はそのまま通す
            alive.append(p)
            continue
        fields = live.get(key)
        if fields is None:
            obsolete.append(p)
            continue
        p = {**p, **{k: v for k, v in fields.items() if k != "type"}}
        alive.append(p)
    return alive, obsolete


def append(cfg: dict, fresh: list[dict]) -> None:
    if not fresh:
        return
    path = cfg["_root"] / "data" / "proposals.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        for p in fresh:
            fp.write(json.dumps(p, ensure_ascii=False) + "\n")


def run(cfg: dict, as_json: bool) -> None:
    """単体実行: 何が提案されるかを確認する（proposals.jsonl へは書かない）。"""
    notes = lint.load_notes(cfg)
    fresh = build(cfg, notes, lint.analyze(cfg, notes))
    if as_json:
        print(json.dumps(fresh, ensure_ascii=False, indent=1, default=str))
        return
    hist: dict[str, int] = {}
    for p in fresh:
        hist[p["type"]] = hist.get(p["type"], 0) + 1
    print(f"== garden rules == 新規の規則ベース提案 {len(fresh)} 件 {hist or '（なし）'}")
    for p in fresh:
        print(f"  - [{p['type']}] {p['target']}")
        print(f"      {p['rationale']}")
    print("\n（この一覧は確認用。実際に proposals.jsonl へ積むのは garden sheet）")
