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
.venv/bin/python -m garden report             # 確信度≥5 でふるい、上位5件を提案レポート化（M4・旧体裁）
.venv/bin/python -m garden rules              # 規則ベースの提案を確認（R4・書き込みなし）
.venv/bin/python -m garden sheet              # 週次の判定シートを生成（文献リンク + 規則ベース）
.venv/bin/python -m garden collect <sheet>    # チェックを回収して decisions に記録
.venv/bin/python -m garden lint --proposals   # 機械照合と健康診断（+ 提案の適用前提チェック）
```

依存: index は標準ライブラリのみ（Python 3.11+）、candidates 以降は `.venv`（numpy）。
埋め込みは Ollama + `bge-m3-8k`（`ollama create bge-m3-8k -f Modelfile.bge-m3-8k` で作成）。
判定は DGX の LLM-jp-4（`config.toml` の `[judge]`）。設定は `config.toml`、出力は `data/`（git 管理外）。

## 状態（2026-08-03）

- **R1+R2 実装完了（2026-08-03）**: 判定シート駆動の庭仕事の基盤 — `garden sheet`（判定シート生成・安定ID・放置順/Inbox,Seeding優先）・
  `garden collect`（チェック回収・編集検出・decisions/decisions_v2 両書き）・`garden lint`（機械照合と健康診断。リンク切れは
  「起票待ちキュー」として扱う）・`garden stats`（採用率集計）。M5 週次レポート再設計はこの sheet 形式に置換して完了。
  設計正本は vault 側 `_Reports/2026-08-03 Robots拡張プラン（判定シート駆動の庭仕事）.md`。R3 apply 以降は Q1〜Q5 の回答待ち。
- **R4 実装完了（2026-08-03）**: 規則ベースの提案生成 `garden rules` を追加し、`garden sheet` が2系統（connector 由来の
  文献リンク + rules 由来の成熟度・タグ・起票待ちキュー）を1枚に載せるようにした。findings が無い環境でも規則ベースだけで
  シートが生える（判定 LLM に届かない Mac でも週次が回る）。同じ指摘を毎週出さないよう `rule_key` で重複を抑止し、
  シート内の枠は `[rules] sheet_quota` で確保する。実測: 昇格候補20件・降格1件を提案化、シート5件生成→ collect が
  採用/却下を正しく分類（lint --proposals 不整合0）。
- **提案本文の書き方（2026-08-03 バッチ2 の返却で確定）**: 親＝ノート自身の主張／タブ1つ下げた子＝文献の引用[[リンク]]や帰結。
  リンク先を読めば分かる定義・手順・列挙は再掲しない。同じ文献箇所を複数ノートで繰り返し引用しない。双方向リンクは目的にしない。
  原典が扱っていない主題に原典を接続しない。未決は断定せず「未定。候補は◯◯」と書く。複数行を生成する種目（draft/merge/spawn）で必須。

## 旧状態（2026-07-11）

- **Phase 1（M0–M4）実装完了・M6 判定側の DGX 本配線と回帰確認まで済み**。
- **PKG運用改善設計 確定（2026-07-11）**: M5 は「週次庭仕事フロー」として実装する — Zettel 起点の優先度選定（放置期間・Inbox/Seeding 優先）・一枚のレビューノート体裁（根拠引用＋貼るだけ wikilink＋採/否チェックボックス）・チェックボックス回収→`data/decisions.jsonl`・launchd 週次自動実行（MBP）。
  設計正本は vault 側 `_Reports/2026-07-11 PKG運用改善設計（週次庭仕事フロー）.md`。あわせて vault の `zettel_linked` は全廃（O8 撤回・受け皿は decisions.jsonl）。
- **O11 決着（2026-07-07）: MBP への移設完了**。MBP 上で venv・Ollama(bge-m3-8k)・`garden index`（notes 796・chunks 2589）を構築し、
  `judge --regress` が Neo 実測基準と一致（gold一致 17/20・非gold link 11/15・JSON妥当 30/35）。残りは週次運用（M5）。
- 次の一手の正本は `HANDOFF.md`（環境別欄の常設ボード・2026-07-07 導入。dev-hub 管理下）。
- **O2 決着**: `bge-m3-8k` 採用（recall@10=51.1% / @30=63.8%）。ruri-large は 512tok 制約で 25.5% に劣後。
- **O10 決着**: DGX は llama.cpp llama-server、モデル `llm-jp-4-32b-a3b-thinking-Q4_K_M.gguf`。
  thinking の推論は `reasoning_content` に分離され `content` は素の JSON。`json_object` 強制は 400 で不可→プロンプト強制＋リトライ。
- **O1 決着**: 埋め込み=MBP / 判定=DGX / robot 本体=MBP。
- **M6 回帰の要注意所見**: LLM-jp-4 は過剰リンク傾向（非gold link 11/15、Claude 代役は 1/15）。
  → **report は確信度≥5 でふるう**（`[report] min_confidence`）。ふるい後の上位5件は全て的確。詳細 `docs/M6-回帰結果-LLMjp4.md`。
- 較正セット（`eval/calibration_export.json` + `calibration_labels.jsonl`）は凍結。モデル差し替え時の回帰テストに使う。
- 次: **M5 週次運用**（index → candidates → judge → report → 週末レビュー、採否を `data/decisions.jsonl` へ）。
