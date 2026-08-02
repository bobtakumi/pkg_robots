"""garden collect — 判定シートの回収（拡張プラン R1）。

人間がチェック・微修正して返したシートを読み、採否を決定記録に落とす。
シートから読むのは sheet.py が埋めた2つの目印だけ:
  `<!-- after: p-… -->` + 直後のコードブロック → 提案の最終形（生成時と違えば edited）
  `<!-- id: p-… -->`    + 直後の連続チェックボックス行 → 採用 / 却下 / 保留

書き出しは2本立て:
  data/decisions.jsonl    既存スキーマ（zettel_path / lit_path / human）。candidates.py の
                          読み側互換を保つため lit_link のみ・edited は accepted 扱いで記録する
  data/decisions_v2.jsonl 全タイプ共通（proposal_id / type / human / edited_after / collected_at）
両方チェック済み・どちらも空は「保留」として記録しない（次回シートに再掲される）。
"""

import json
import re
from datetime import datetime
from pathlib import Path

AFTER_RE = re.compile(r"<!--\s*after:\s*(p-[\w-]+)\s*-->\s*\n(`{3,})[^\n]*\n(.*?)\n\2", re.S)
ID_RE = re.compile(r"<!--\s*id:\s*(p-[\w-]+)\s*-->")
CHECK_RE = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.*)$")


def parse_sheet(text: str) -> dict[str, dict]:
    """{proposal_id: {"checked": [ラベル…], "after": 最終形 or None}}。"""
    out: dict[str, dict] = {}
    for m in AFTER_RE.finditer(text):
        out.setdefault(m.group(1), {})["after"] = m.group(3).strip()

    lines = text.splitlines()
    marks = [(i, ID_RE.search(l).group(1)) for i, l in enumerate(lines) if ID_RE.search(l)]
    for i, pid in marks:
        checked: list[str] = []
        for line in lines[i + 1:]:
            c = CHECK_RE.match(line)
            if c:
                if c.group(1).lower() == "x":
                    checked.append(c.group(2).strip())
            elif line.strip():
                break  # チェックボックス群の終わり（空行は挟んでよい）
        out.setdefault(pid, {})["checked"] = checked
    return out


def classify(entry: dict, proposal: dict) -> tuple[str, str | None]:
    """(判定, edited_after)。判定は accepted / rejected / edited / pending / conflict。"""
    checked = entry.get("checked", [])
    yes = any("採用" in c or "採る" in c for c in checked)
    no = any("却下" in c or "見送" in c for c in checked)
    if yes and no:
        return "conflict", None
    if no:
        return "rejected", None
    if not yes:
        return "pending", None
    after = entry.get("after")
    if after is not None and after.strip() != (proposal.get("after") or "").strip():
        return "edited", after
    return "accepted", None


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def run(cfg: dict, sheet_path: Path, dry_run: bool) -> None:
    root: Path = cfg["_root"]
    proposals = {p["id"]: p for p in load_jsonl(root / "data" / "proposals.jsonl")}
    already = {d["proposal_id"] for d in load_jsonl(root / "data" / "decisions_v2.jsonl")}
    parsed = parse_sheet(sheet_path.read_text(encoding="utf-8").replace("\r\n", "\n"))

    counts = {"accepted": 0, "rejected": 0, "edited": 0, "pending": 0,
              "conflict": 0, "unknown": 0, "duplicate": 0}
    v2_rows, v1_rows, log = [], [], []
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for pid, entry in parsed.items():
        p = proposals.get(pid)
        if p is None:
            counts["unknown"] += 1
            log.append(f"  ? {pid}: proposals.jsonl に無い提案（シートが古い可能性）")
            continue
        verdict, edited = classify(entry, p)
        counts[verdict] += 1
        if verdict in ("pending", "conflict"):
            if verdict == "conflict":
                log.append(f"  ! {pid}: 採用と却下の両方にチェック → 保留扱い")
            continue
        if pid in already:
            counts["duplicate"] += 1
            log.append(f"  = {pid}: 記録済みのため再記録しない")
            continue
        v2_rows.append({"proposal_id": pid, "type": p["type"], "human": verdict,
                        "edited_after": edited, "collected_at": now})
        if p["type"] == "lit_link" and p.get("source_refs"):
            v1_rows.append({"zettel_path": p["target"], "lit_path": p["source_refs"][0],
                            "human": "accepted" if verdict == "edited" else verdict})
        log.append(f"  - {pid}: {verdict}"
                   + (f"\n      → {edited}" if edited else ""))

    print(f"== garden collect == {sheet_path}")
    print(f"提案 {len(parsed)} 件: 採用 {counts['accepted']} / 却下 {counts['rejected']} / "
          f"編集 {counts['edited']} / 保留 {counts['pending'] + counts['conflict']}")
    for line in log:
        print(line)
    if dry_run:
        print(f"[dry-run] 書き込みなし（記録対象 {len(v2_rows)} 件）")
        return
    if not v2_rows:
        print("記録対象なし")
        return
    with (root / "data" / "decisions_v2.jsonl").open("a", encoding="utf-8") as fp:
        for r in v2_rows:
            fp.write(json.dumps(r, ensure_ascii=False) + "\n")
    if v1_rows:
        with (root / "data" / "decisions.jsonl").open("a", encoding="utf-8") as fp:
            for r in v1_rows:
                fp.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"→ data/decisions_v2.jsonl に {len(v2_rows)} 行"
          f"（うち lit_link {len(v1_rows)} 行を data/decisions.jsonl にも）")
