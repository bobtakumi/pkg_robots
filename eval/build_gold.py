"""6/26 人力レポートから較正用正解データ eval/gold_pairs.yaml を再生成する。

正例 = 出典別テーブルの確度「高」行（zettel → 文献ノート）。
負例 = レポート冒頭「重要な訂正」の DS 誤接続（judge の few-shot 負例用）。
YAML は書き出しのみなので stdlib で直接整形する（依存追加なし）。

【正本について】eval/gold_pairs.yaml が較正データの**凍結正本**（git 管理・コミット済み）。
本スクリプトは「生成元レポートが vault に存在する間の再生成手段」にすぎない。
生成元レポート（_Reports/2026-06-26 …）は plan/20 規約上いずれ削除されうる使い捨てだが、
その時点で gold_pairs.yaml は既に凍結済みなので較正の再現性は失われない。
生成元パスは config.toml の vault.path から導出する（絶対パス直書きを廃止）。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from garden import config

REPORT_REL = "_Reports/2026-06-26 文献層リンク候補（クロスレイヤー接続）.md"
OUT = Path(__file__).parent / "gold_pairs.yaml"

SOURCE_HEAD_RE = re.compile(r"^#### \[\[(.+?)\]\]（(.+?)）")
ROW_RE = re.compile(r"^\| \[\[(.+?)\]\] \| (.+?) \| (.+?) \| 高 \|$")
LINK_RE = re.compile(r"\[\[([^\]|#]+)")


def main() -> None:
    cfg = config.load()
    report = Path(cfg["vault"]["path"]) / REPORT_REL
    if not report.exists():
        sys.exit(f"生成元レポートが無い: {report}\n"
                 "（凍結正本 gold_pairs.yaml が既にあるなら再生成は不要）")
    text = report.read_text(encoding="utf-8")
    source = ""
    positives = []
    for line in text.splitlines():
        m = SOURCE_HEAD_RE.match(line)
        if m:
            source = m.group(2).split("）")[0].strip("※ ")
            continue
        m = ROW_RE.match(line)
        if m:
            zettel, targets_cell, reason = m.groups()
            targets = [t.strip() for t in LINK_RE.findall(targets_cell)]
            if targets:
                positives.append((zettel.strip(), targets, source, reason.strip()))
    if not positives:
        sys.exit("正例が抽出できない。レポートの表形式が変わった可能性")

    def q(s: str) -> str:
        return '"' + s.replace('"', '\\"') + '"'

    lines = [
        "# 較正用正解データ（凍結正本・git 管理）。手編集しない。",
        "# 生成元: _Reports/2026-06-26 文献層リンク候補（クロスレイヤー接続）",
        "# 再生成: .venv/bin/python eval/build_gold.py（生成元レポートが vault に在る間のみ）",
        "positives:",
    ]
    for zettel, targets, source, reason in positives:
        lines.append(f"  - zettel: {q(zettel)}")
        lines.append("    targets:")
        lines += [f"      - {q(t)}" for t in targets]
        lines.append(f"    source: {q(source)}")
        lines.append(f"    reason: {q(reason)}")
    lines += [
        "negatives:  # judge few-shot 用の誤接続予防例（6/26 レポート「重要な訂正」）",
        '  - zettel: "底が1以上であることを保証するのがDSの役割"',
        '    wrong_target_hint: "GPU系出典（PMPP・Triton 等）"',
        '    reason: "本文の DS はデータサイエンティスト（AI駆動BPR文脈）であり GPU-sensei ではない"',
        '  - zettel: "指数関数の底を必ず1以上にする"',
        '    wrong_target_hint: "GPU系出典（PMPP・Triton 等）"',
        '    reason: "同上。表層語彙の一致（DS/指数）による誤接続の典型例"',
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    n_targets = sum(len(t) for _, t, _, _ in positives)
    print(f"正例 {len(positives)} zettel（target 延べ {n_targets}）→ {OUT.name}")


main()
