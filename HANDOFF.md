# HANDOFF — pkg_robots（環境別欄の常設ボード）

_`CLAUDE.md` から自動読込される**次の一手の正本**（dev-hub 側 `projects/pkg-robots.md` は状態をコピーしない）。
セッションを終える側は各欄を実状態へ更新し、**持ち運び端末（Neo 等オフライン可の環境）の欄を絶やさず**
commit & push する（不変条件）。環境構築の手順そのもの（venv・Ollama・索引・回帰）は `docs/HANDOFF-MBP.md` を参照。_

## Neo（Mac・GPU なし・オフライン可）

- [ ] **週次レポートの再設計実装**（設計正本: `~/pkg_vault/_Reports/2026-07-11 PKG運用改善設計（週次庭仕事フロー）.md`）:
  ① 対象 Zettel の優先度選定（最終編集日が古い順・Inbox / Seeding 状態を優先。状態値の実体は vault frontmatter/フォルダを実装時に確認）、
  ② レポート体裁を「一枚のレビューノート」へ（根拠引用＋貼るだけ wikilink＋採/否チェックボックス、出力先 `_Reports/garden-weekly-YYYYMMDD.md`）。
  確認: `garden report` が新体裁のノートを生成する（実装はオフライン可・実 LLM 不要、判定済み findings で確認）。
  実装メモ（2026-07-11 引き継ぎ）:
  - 体裁変更は `garden/report.py`（vault へ書く唯一のパス）。チェックボックスは提案の安定 ID を HTML コメント等で行に埋め、後述の回収コマンドが機械的に読めるようにする。
  - 優先度選定は report 段の並べ替えなら最小、`garden/candidates.py` 段の絞り込みなら judge コストも減る。zettel の最終編集日・層分類は `garden index` が `data/garden.db` に持つはず（スキーマは `garden/index.py` で確認）。
  - **vault の `zettel_linked` は 2026-07-11 に全廃済み（O8 撤回）。実装で参照しないこと。** 採否の受け皿は `data/decisions.jsonl` のみ。
  - `decisions.jsonl` は**読み側が実装済み**（`garden/candidates.py` が `human=="rejected"` のペアを候補から除外）。回収コマンドの書き出しスキーマは既存の読み側（`zettel_path` / `lit_path` / `human`）に合わせる。
  - confidence≥5 ゲート・judge まわりの禁止事項（CLAUDE.md「触ってはいけないもの」）は変更しない。
- [ ] **M5 の未実装 2 点に着手**: `garden stats`（`data/decisions.jsonl` の採用率集計）と、提案への安定 ID 付与（decisions との突合用）。
  採否はレビューノートのチェックボックス状態を回収して `decisions.jsonl` へ記録する方式に決着（2026-07-11 設計判断）。回収コマンドもここで実装。
  仕様は vault 側実装プラン §M5（`~/pkg_vault/_Reports/2026-07-02 Robots実装プラン Phase1（インデクサ+Connector）.md`）。
  確認: `.venv/bin/python -m garden stats` が採用率を表示する（実装はオフライン可・実 LLM 不要）。

## MBP（M3 Max・埋め込みホスト・robot 本体）

- [ ] **稼働・疎通の事前チェック**（2026-07-11 時点で MBP は Tailscale 上オフライン＝まず復帰。レポート再設計の実装とは独立に進められる）:
  ① MBP をネットワーク復帰させ、Tailscale で bobmbp が active になること（スリープ／Tailscale 停止／省電力設定を疑う。週次自動実行はこれの常時成立が前提）。
  ② vault 同期: Neo に 2026-07-11 の未 push コミットが12件以上ある（設計正本・整合性掃討）。MBP 復帰後、Neo で Obsidian を開けば obsidian-git が自動 push（手動なら Neo で `git -C ~/pkg_vault push`）→ MBP の vault 作業コピーで pull。
  ③ MBP で `~/pkg_robots` と `~/dev-hub` を `git pull`（本引き継ぎと実装メモを取得）。
  ④ DGX 到達: `curl -s --max-time 6 http://spark-062c.local:11434/v1/models` がモデルを返す。⑤ Ollama 常駐＋`bge-m3-8k` が存在。
  ⑥ vault 同期後に `python -m garden index` を再実行。期待値は notes 780 前後（従来 796 から 2026-07-11 の整合性掃討で PMPP スタブ16件が削除済み）・zettel 124・chunks 全埋め込み。
  大きくズレたら `judge --regress` で基準（JSON妥当 29/35・gold 17/20・非gold link 11/15）からの悪化を確認。
  ※ Neo クローンの `data/` はプロト由来で本番 `findings.json` 未生成。本番サイクルは MBP 側で回す。
- [ ] **M5 週次サイクルの初回本番実行**（手順は `docs/HANDOFF-MBP.md` §3.6、レポート再設計の実装後は新体裁で）:
  `candidates` → `judge --limit 40` → `report`。
  確認: `~/pkg_vault/_Reports/` に週次ノートが生成され、上位5件が confidence≥5 でゲートされていること。実行後 vault 側を commit/push。
  ※ 環境構築（§3.1–3.5）は 2026-07-07 完了済み — index 再構築（notes 796・chunks 2589 全埋め込み）、judge 回帰が Neo 基準一致（gold 17/20・非gold link 11/15・JSON妥当 30/35）。
- [ ] **週次自動実行のセットアップ**（初回本番実行の後）: launchd で毎週決まった曜日に `candidates → judge → report` を自動実行し、レビューノートが人手なしで生える状態にする（MBP 常時稼働前提・2026-07-11 設計判断）。
  確認: 指定曜日に週次ノートが自動生成される。

## Spark（DGX・GPU 実行）

- [ ] なし（llama-server で LLM-jp-4 を提供し続けるのみ。疎通確認: `curl http://spark-062c.local:11434/v1/models`）。

## 保留・意思決定待ち（ユーザー入力が要るもの）

- [ ] **レビューバンドル判定待ち**: `docs/review-bundles/2026-07-07_mbp-onboarding/views/review.md`（RP 5 個・想定 5 分）。
  MBP 移設＋オンボーディングの構成判断の事後承認。✏️/❌ が出たら core を直して view 再派生。
- [ ] **（週次フロー2〜3週運用後）判定モデル実験**: 凍結較正セット35ペアで LLM-jp-4 / DS4（DeepSeek ローカル）/ Claude gold の三つ巴比較。結果を見て confidence≥5 ゲートの緩和可否を再検討（過剰提案は許容の回答あり 2026-07-11。ただし提案洪水は過去の頓挫要因のためフロー定着を先行）。
  ※ 採否記録の運用方法は決着済み（2026-07-11）: レビューノートのチェックボックス状態を robots が回収して `decisions.jsonl` へ記録。設計正本は `~/pkg_vault/_Reports/2026-07-11 PKG運用改善設計（週次庭仕事フロー）.md`。

## 参照

- 全体感・追記ログ: dev-hub `projects/pkg-robots.md`
- 状態の正本: `README.md`（フェーズ・決着事項）＋このファイル（次の一手）。環境構築の手順は `docs/HANDOFF-MBP.md`（一回性文書）。
