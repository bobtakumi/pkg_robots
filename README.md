# pkg_robots — Robots in the Garden 実装（Phase 1）

PKG（`~/pkg_vault`）に対する Connector robot とその土台。**Vault へは read + propose**
（書き込みは `_Reports/suggest-YYYYMMDD.md` のみ）。

> **初めての人・MBP で再開する人は、まず [`docs/00-START-HERE.md`](docs/00-START-HERE.md) を読む。**
> プロジェクトの全体像・経緯・落とし穴を案内している。セットアップ手順は [`docs/HANDOFF-MBP.md`](docs/HANDOFF-MBP.md)。
> 設計判断の正典は Vault 側のプロジェクトノート v4 と実装プラン（START-HERE §9 にパス）。

## 使い方

```sh
.venv/bin/python -m garden index              # 索引＋統計の全再構築（埋め込み込み。Ollama 未起動なら自動スキップ）
.venv/bin/python -m garden candidates --eval  # 候補生成 + recall ゲート測定（M2）
.venv/bin/python eval/rank_diag.py            # 正解ペアの順位分布診断（モデル比較用）
.venv/bin/python -m garden judge --limit 40   # 候補を LLM-jp-4 で判定（M3）
.venv/bin/python -m garden judge --regress eval/calibration_export.json  # 較正セットで回帰（M6）
.venv/bin/python -m garden report             # 確信度≥5 でふるい、上位5件を提案レポート化（M4）
```

依存: index は標準ライブラリのみ（Python 3.11+）、candidates 以降は `.venv`（numpy）。
埋め込みは Ollama + `bge-m3-8k`（`ollama create bge-m3-8k -f Modelfile.bge-m3-8k` で作成）。
判定は DGX の LLM-jp-4（`config.toml` の `[judge]`）。設定は `config.toml`、出力は `data/`（git 管理外）。

## 状態（2026-07-06）

- **Phase 1（M0–M4）実装完了・M6 判定側の DGX 本配線と回帰確認まで済み**。残りは MBP への移設（O11）と週次運用（M5）。
- **O2 決着**: `bge-m3-8k` 採用（recall@10=51.1% / @30=63.8%）。ruri-large は 512tok 制約で 25.5% に劣後。
- **O10 決着**: DGX は llama.cpp llama-server、モデル `llm-jp-4-32b-a3b-thinking-Q4_K_M.gguf`。
  thinking の推論は `reasoning_content` に分離され `content` は素の JSON。`json_object` 強制は 400 で不可→プロンプト強制＋リトライ。
- **O1 決着**: 埋め込み=MBP / 判定=DGX / robot 本体=MBP。
- **M6 回帰の要注意所見**: LLM-jp-4 は過剰リンク傾向（非gold link 11/15、Claude 代役は 1/15）。
  → **report は確信度≥5 でふるう**（`[report] min_confidence`）。ふるい後の上位5件は全て的確。詳細 `docs/M6-回帰結果-LLMjp4.md`。
- 較正セット（`eval/calibration_export.json` + `calibration_labels.jsonl`）は凍結。モデル差し替え時の回帰テストに使う。
- 次: **M5 週次運用**（index → candidates → judge → report → 週末レビュー、採否を `data/decisions.jsonl` へ）。
