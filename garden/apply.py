"""garden apply — 承認済み提案を Vault へ反映する（拡張プラン R3）。

Q1 の回答（2026-08-03 ユーザー確定）: **robots に `2_Permanent/` への書き込みを許す。
ただし人間が確認した提案だけ**。つまり適用対象は `decisions_v2.jsonl` で accepted / edited に
なった提案に限る。判定を経ていない提案には一切触れない。

Q5 の安全側の既定もそのまま採る: before が現在の本文と**一字一致するときだけ**機械適用し、
ずれていたら適用せず差し戻す（人間が文脈を見て直す）。ノートは編集され続けるので、
シートを作った時点との差分を黙って上書きしないための歯止め。

適用の種目:
  lit_link / perm_link  before があれば置換、無ければ本文末尾に追加
  status / tag          frontmatter の1行を置換
  queue                 新規ノートを作成（既に在れば skip）

既定は dry-run。`--write` を付けたときだけ書き込む。書き込み前に Obsidian の起動を確認し、
起動中なら中止する（obsidian-git の自動コミットと交錯するため。vault 側 CLAUDE.md の規約）。
"""

import json
import subprocess
from datetime import date, datetime
from pathlib import Path

from . import lint

APPLICABLE = {"accepted", "edited"}
FM_TYPES = {"status", "tag"}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def obsidian_running() -> bool:
    r = subprocess.run(["pgrep", "-x", "Obsidian"], capture_output=True)
    return r.returncode == 0


def pending(root: Path) -> list[tuple[dict, str | None]]:
    """(proposal, 適用する after) の列。採否済みかつ未適用のものだけ。"""
    props = {p["id"]: p for p in load_jsonl(root / "data" / "proposals.jsonl")}
    done = {a["proposal_id"] for a in load_jsonl(root / "data" / "applied.jsonl")}
    out = []
    for d in load_jsonl(root / "data" / "decisions_v2.jsonl"):
        if d["human"] not in APPLICABLE or d["proposal_id"] in done:
            continue
        p = props.get(d["proposal_id"])
        if p is None:
            continue
        out.append((p, d.get("edited_after") or p.get("after")))
    return out


def plan_one(p: dict, after: str | None, text: str | None) -> dict:
    """1件の適用計画。実行はしない。

    `text` は適用直前の対象ファイルの中身（存在しなければ None）。同じファイルへ複数の提案が
    当たるので、呼び出し側は1件適用するたびに最新の中身を渡す（古い版から作った計画で
    上書きしないため）。
    """
    res = {"id": p["id"], "type": p["type"], "target": p["target"], "action": None,
           "reason": None, "new_text": None}
    if after is None:
        res["reason"] = "after が空"
        return res

    if p["type"] == "queue":
        if text is not None:
            res["reason"] = "既に存在する（起票済み）"
            return res
        res["action"], res["new_text"] = "create", after.rstrip("\n") + "\n"
        return res

    if text is None:
        res["reason"] = "target が無い"
        return res
    fm, body = lint.split_frontmatter(text)
    before = (p.get("before") or "").rstrip("\n")

    if p["type"] in FM_TYPES:
        if not before:
            res["reason"] = "frontmatter の置換に before が要る"
            return res
        if fm.count(before) != 1:
            res["reason"] = f"before が frontmatter と一致しない（{fm.count(before)} 箇所）"
            return res
        res["action"] = "replace-fm"
        res["new_text"] = text.replace(before, after.rstrip("\n"), 1)
        return res

    after = after.rstrip("\n")
    if before:
        if body.count(before) != 1:
            res["reason"] = f"before が本文と一致しない（{body.count(before)} 箇所）"
            return res
        res["action"] = "replace"
        res["new_text"] = text.replace(before, after, 1)
    else:
        res["action"] = "append"
        res["new_text"] = text.rstrip("\n") + "\n" + after + "\n"
    return res


def bump_modified(text: str, today: str) -> str:
    """frontmatter の modified を当日へ（Linter の後追い注入を避ける既存規約に合わせる）。"""
    lines = text.split("\n")
    for i, line in enumerate(lines[:20]):
        if line.startswith("modified:"):
            lines[i] = f"modified: {today}"
            break
    return "\n".join(lines)


def run(cfg: dict, write: bool, do_commit: bool) -> None:
    root: Path = cfg["_root"]
    vault = Path(cfg["vault"]["path"])
    items = pending(root)
    if not items:
        print("適用対象なし（採否済みで未適用の提案がない）")
        return

    # 同じファイルに複数当たるので、計画は1件ずつ「直前の状態」に対して立てる
    overlay: dict[str, str | None] = {}

    def current(rel: str) -> str | None:
        if rel not in overlay:
            path = vault / rel
            overlay[rel] = path.read_text(encoding="utf-8") if path.exists() else None
        return overlay[rel]

    plans = []
    for p, after in items:
        plan = plan_one(p, after, current(p["target"]))
        if plan["action"]:
            overlay[p["target"]] = plan["new_text"]
        plans.append(plan)
    ok = [p for p in plans if p["action"]]
    skipped = [p for p in plans if not p["action"]]

    print(f"== garden apply == 採否済み・未適用 {len(plans)} 件 → 適用可 {len(ok)} / 差し戻し {len(skipped)}")
    for p in ok:
        print(f"  + [{p['type']}/{p['action']}] {p['target']}  ({p['id']})")
    for p in skipped:
        print(f"  ! [{p['type']}] {p['target']}  ({p['id']}): {p['reason']}")

    if not write:
        print("\n[dry-run] 書き込みなし。実行するなら --write を付ける")
        return
    if not ok:
        print("適用可能な提案がないので何もしない")
        return
    if obsidian_running():
        print("\n中止: Obsidian が起動中。obsidian-git の自動コミットと交錯するので先に終了する")
        return

    today = date.today().isoformat()
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    created = {p["target"] for p in ok if p["action"] == "create"}
    touched: list[str] = []
    with (root / "data" / "applied.jsonl").open("a", encoding="utf-8") as log:
        for p in ok:
            log.write(json.dumps({"proposal_id": p["id"], "type": p["type"],
                                  "target": p["target"], "action": p["action"],
                                  "applied_at": now}, ensure_ascii=False) + "\n")
        for rel in dict.fromkeys(p["target"] for p in ok):  # 同一ファイルは最終形を1回だけ書く
            text = overlay[rel]
            if rel not in created:
                text = bump_modified(text, today)
            path = vault / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            touched.append(rel)
    print(f"\n{len(touched)} ファイルを更新した（提案 {len(ok)} 件）")

    if do_commit:
        msg = f"lit: 承認済み提案を適用（{len(touched)}件・garden apply {today}）"
        subprocess.run(["git", "-C", str(vault), "add", "--"] + touched, check=True)
        subprocess.run(["git", "-C", str(vault), "commit", "-q", "-m", msg], check=True)
        print(f"コミットした: {msg}（push はしない）")
    else:
        print("コミットはしていない（--commit で vault 側にコミットを作る）")
