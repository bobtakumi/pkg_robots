# HANDOFF — pkg_robots（環境別欄の常設ボード）

_`CLAUDE.md` から自動読込される**次の一手の正本**（dev-hub 側 `projects/pkg-robots.md` は状態をコピーしない）。
セッションを終える側は各欄を実状態へ更新し、**持ち運び端末（Neo 等オフライン可の環境）の欄を絶やさず**
commit & push する（不変条件）。環境構築の手順そのもの（venv・Ollama・索引・回帰）は `docs/HANDOFF-MBP.md` を参照。_

## Neo（Mac・GPU なし・オフライン可）

- [ ] **M5 の未実装 2 点に着手**: `garden stats`（`data/decisions.jsonl` の採用率集計）と、提案への安定 ID 付与（decisions との突合用）。
  仕様は vault 側実装プラン §M5（`~/pkg_vault/_Reports/2026-07-02 Robots実装プラン Phase1（インデクサ+Connector）.md`）。
  確認: `.venv/bin/python -m garden stats` が採用率を表示する（実装はオフライン可・実 LLM 不要）。

## MBP（M3 Max・埋め込みホスト・robot 本体）

- [ ] **M5 週次サイクルの初回本番実行**（手順は `docs/HANDOFF-MBP.md` §3.6）:
  `candidates` → `judge --limit 40` → `report`。
  確認: `~/pkg_vault/_Reports/suggest-YYYYMMDD.md` が生成され、上位5件が confidence≥5 でゲートされていること。実行後 vault 側を commit/push。
  ※ 環境構築（§3.1–3.5）は 2026-07-07 完了済み — index 再構築（notes 796・chunks 2589 全埋め込み）、judge 回帰が Neo 基準一致（gold 17/20・非gold link 11/15・JSON妥当 30/35）。

## Spark（DGX・GPU 実行）

- [ ] なし（llama-server で LLM-jp-4 を提供し続けるのみ。疎通確認: `curl http://spark-062c.local:11434/v1/models`）。

## 保留・意思決定待ち（ユーザー入力が要るもの）

- [ ] **レビューバンドル判定待ち**: `docs/review-bundles/2026-07-07_mbp-onboarding/views/review.md`（RP 5 個・想定 5 分）。
  MBP 移設＋オンボーディングの構成判断の事後承認。✏️/❌ が出たら core を直して view 再派生。
- [ ] 週次レポートの採否記録（`data/decisions.jsonl`）の運用方法: 記入は人間 or 人間指示下の代筆。初回レポート生成後にレビューの回し方を決める。

## 参照

- 全体感・追記ログ: dev-hub `projects/pkg-robots.md`
- 状態の正本: `README.md`（フェーズ・決着事項）＋このファイル（次の一手）。環境構築の手順は `docs/HANDOFF-MBP.md`（一回性文書）。
