"""garden report — 提案レポート生成（実装プラン M4）。

findings（judge の link 判定）から上位数件を選び、Vault の
`_Reports/suggest-YYYYMMDD.md` に提案レポートを書く（plan/20 の形式を継承）。

**sheet へ移行済み。週次は `garden sheet`（判定シート）を使う**（このファイルは互換のため残置）。

Ch9 トーン: 少数（上限5件）・非一括・使い捨てレポート。リンクの実挿入は常に人間。
Vault への書き込み例外パスの一つ（もう一つは sheet.py の garden-weekly）。
"""

import json
import sys
from datetime import date
from pathlib import Path

MAX_PROPOSALS = 5

HEADER = """---
type: report
title: "リンク提案 {today}（Connector robot）"
created: {today}
modified: {today}
tags: [report, PKG運用, suggest]
---

# リンク提案 {today} — Connector robot

> 週次のリンク提案（上限{cap}件）。**採否の判断とリンクの記入は常に人間**。
> このレポートは使い捨て——読んだらアーカイブ/削除してよい。採用する知識はリンクとして Vault に書く。
> 生成: pkg_robots `garden report`（判定: {judge_note}）
"""

ENTRY = """
## 候補{n}: [[{zettel}]] ⇄ [[{lit}]]（確度: {conf}/5・{relation}）

- 接続理由: {reason}
- zettel 側の根拠: 「{ev_z}」
- 文献側の根拠: 「{ev_l}」
- 提案リンク文（zettel 本文 or 文献索引ノートの `zettel_linked` へ・記入は人間）:
  - `[[{lit}]]`（{relation}）
"""


def run(cfg: dict, findings_path: Path | None, judge_note: str = "config の judge モデル") -> None:
    root: Path = cfg["_root"]
    src = findings_path or (root / "data" / "findings.json")
    findings = json.loads(src.read_text(encoding="utf-8"))
    # confidence ゲート: M6 回帰（2026-07-04）で LLM-jp-4 が過剰リンク（非gold link 11/15）と判明。
    # 誤リンクは conf4〜5、正リンクも 4〜5 だが、conf>=5 に絞ると偽 11→2 / 正 17→9。
    # 週5件の提案では recall より precision を優先するため、既定で conf>=5 を採用。
    min_conf = cfg.get("report", {}).get("min_confidence", 5)
    all_links = [f for f in findings if f.get("verdict") == "link"]
    links = [f for f in all_links if f.get("confidence", 0) >= min_conf]
    if not links:
        sys.exit(f"confidence>={min_conf} の link が0件"
                 f"（link 総数 {len(all_links)}）。閾値を下げるか judge を見直すこと")
    links.sort(key=lambda f: (-f.get("confidence", 0), -f.get("score", 0)))
    picked = links[:MAX_PROPOSALS]

    today = date.today().isoformat()
    parts = [HEADER.format(today=today, cap=MAX_PROPOSALS, judge_note=judge_note)]
    for i, f in enumerate(picked, 1):
        parts.append(ENTRY.format(
            n=i, zettel=f["zettel_title"], lit=f["lit_title"],
            conf=f.get("confidence", "?"), relation=f.get("relation", "?"),
            reason=f.get("reason", ""),
            ev_z=f.get("evidence_zettel", ""), ev_l=f.get("evidence_lit", "")))
    parts.append(f"\n---\n残り候補 {len(links) - len(picked)} 件は次回以降に持ち越し"
                 f"（少数・非一括の原則）。生成元 findings: `{src.name}`\n")

    out = Path(cfg["vault"]["path"]) / "_Reports" / f"suggest-{today.replace('-', '')}.md"
    out.write_text("".join(parts), encoding="utf-8")
    print(f"提案 {len(picked)} 件（link {len(links)} 件中）→ {out}")
