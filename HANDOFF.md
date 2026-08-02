# HANDOFF — pkg_robots（環境別欄の常設ボード）

_`CLAUDE.md` から自動読込される**次の一手の正本**（dev-hub 側 `projects/pkg-robots.md` は状態をコピーしない）。
セッションを終える側は各欄を実状態へ更新し、**持ち運び端末（Neo 等オフライン可の環境）の欄を絶やさず**
commit & push する（不変条件）。環境構築の手順そのもの（venv・Ollama・索引・回帰）は `docs/HANDOFF-MBP.md` を参照。_

## Neo（Mac・GPU なし・オフライン可）

- [x] ~~週次レポートの再設計実装~~・~~M5 未実装2点（stats・安定ID・回収）~~ → **2026-08-03 実装完了（R1+R2）**。
  `garden sheet / collect / lint / stats` を追加（判定シート生成・チェック回収・機械照合/健康診断・採用率集計）。
  設計正本は `~/pkg_vault/_Reports/2026-08-03 Robots拡張プラン（判定シート駆動の庭仕事）.md`（7/11 設計の M5 を包含）。
  検証済み: 較正 findings からのシート生成・collect の5分類（採用/却下/編集/保留/二重チェック警告）・
  decisions.jsonl 読み側互換・lint の実 vault 走査（起票待ちキュー0・タグ違反0・昇格候補22・完全孤立3）。
  Fable レビュー合格（修正必須なし・推奨4件は反映済み）。
- [ ] **R3 `garden apply` の実装は保留**: vault 書き込み権限（拡張プラン Q1）のユーザー回答待ち。
  回答は vault 側レビューバンドル `~/pkg_vault/_Reports/review-bundles/2026-08-03_robots-gardener-plan/views/review.md`（Q1〜Q5）で受ける。
  なお `lint --proposals` が apply の前提チェック（target 実在・before 一致・リンク解決）として先に動く。
- [ ] **R4 rules proposer**: lint が検出する昇格候補（現在22件）・タグ違反・孤立を「提案」として proposals.jsonl に流し込み、週次シートの種目に加える。
  注意: 昇格はリンク数条件のみ機械判定できる。07 基準の「本文要素2つ以上」は人間判断へ回す設計にする。

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
  `candidates` → `judge --limit 40` → `sheet`（旧 `report` は移行済み・週次は sheet を使う）。週末レビュー後は `collect <シートパス>` → `stats` で採否を回収・集計。
  確認: `~/pkg_vault/_Reports/` に週次ノートが生成され、上位5件が confidence≥5 でゲートされていること。実行後 vault 側を commit/push。
  ※ 環境構築（§3.1–3.5）は 2026-07-07 完了済み — index 再構築（notes 796・chunks 2589 全埋め込み）、judge 回帰が Neo 基準一致（gold 17/20・非gold link 11/15・JSON妥当 30/35）。
- [ ] **週次自動実行のセットアップ**（初回本番実行の後）: launchd で毎週決まった曜日に `candidates → judge → report` を自動実行し、レビューノートが人手なしで生える状態にする（MBP 常時稼働前提・2026-07-11 設計判断）。
  確認: 指定曜日に週次ノートが自動生成される。

## Spark（DGX・GPU 実行）

- [ ] なし（llama-server で LLM-jp-4 を提供し続けるのみ。疎通確認: `curl http://spark-062c.local:11434/v1/models`）。

## 保留・意思決定待ち（ユーザー入力が要るもの）

- [ ] **Robots 拡張プラン（判定シート駆動の庭仕事）の判定待ち**: vault 側 `_Reports/review-bundles/2026-08-03_robots-gardener-plan/views/review.md`（Q1〜Q5・記述回答）。
  Q1=apply の vault 書き込み権限 / Q2=起草の頭脳の呼び出し方 / Q3=優先順 / Q4=シート置き場 / Q5=編集の適用範囲。
  較正資産: 大掃除の統合是非25件を `eval/cleanup_gold_20260802.json` に gold 化済み（R6 アトミック性判定の再現テスト用）。
- [ ] **レビューバンドル判定待ち**: `docs/review-bundles/2026-07-07_mbp-onboarding/views/review.md`（RP 5 個・想定 5 分）。
  MBP 移設＋オンボーディングの構成判断の事後承認。✏️/❌ が出たら core を直して view 再派生。
- [ ] **（週次フロー2〜3週運用後）判定モデル実験**: 凍結較正セット35ペアで LLM-jp-4 / DS4（DeepSeek ローカル）/ Claude gold の三つ巴比較。結果を見て confidence≥5 ゲートの緩和可否を再検討（過剰提案は許容の回答あり 2026-07-11。ただし提案洪水は過去の頓挫要因のためフロー定着を先行）。
  ※ 採否記録の運用方法は決着済み（2026-07-11）: レビューノートのチェックボックス状態を robots が回収して `decisions.jsonl` へ記録。設計正本は `~/pkg_vault/_Reports/2026-07-11 PKG運用改善設計（週次庭仕事フロー）.md`。

## 参照

- 全体感・追記ログ: dev-hub `projects/pkg-robots.md`
- 状態の正本: `README.md`（フェーズ・決着事項）＋このファイル（次の一手）。環境構築の手順は `docs/HANDOFF-MBP.md`（一回性文書）。
