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
- [x] ~~**R3 `garden apply`**~~ → **2026-08-03 実装完了**。Q1 回答（2026-08-03 ユーザー）: **robots の
  `2_Permanent/` 書き込みを許可する。ただしこのチャットと同じく、提案を人間が確認したあとに書き込む**。
  実装は `decisions_v2.jsonl` の accepted / edited のみを対象とし、before が現在の本文と一字一致するときだけ
  機械適用・ずれたら差し戻す（Q5 の安全側）。既定 dry-run、`--write` で書き込み、`--commit` で `lit:` コミット
  （push はしない）。Obsidian 起動中は中止。`data/applied.jsonl` で二重適用を防ぐ。検証は疑似 vault で7項目合格。
  次の一手: 週次サイクルで一度 `sheet → collect → apply --write --commit` を通しで回して本番確認する。
- [x] ~~**R4 rules proposer**~~ → **2026-08-03 実装完了**。`garden rules`（確認用・書き込みなし）を追加し、
  `garden sheet` が文献リンクと規則ベース提案（成熟度 status / タグ tag / 起票待ちキュー queue）を1枚に載せる。
  findings が無くてもシートが生える（判定 LLM 不達の環境で週次が止まらない）。重複抑止は `rule_key`、
  シート内の枠は `[rules] sheet_quota`（既定2）。昇格はリンク数条件のみ機械判定し、07 基準の「本文要素2つ以上」は
  提案文で人間に確認を促す（自動変更しない）。検証済み: 昇格候補20・降格1を提案化 → シート5件 →
  collect が採用/却下を分類 → `lint --proposals` 不整合0。queue 提案は「まだ無いノート」を target にするため
  lint 側で存在チェックを反転させてある。
- [ ] **R4 の残り（moc proposer）**: タグ→MOC の対応表が未確定のため未実装。規則ベースで出すなら config に対応表を持たせる。
  体裁の確定仕様（2026-08-03 ユーザー指示 + バッチ2 の返却）: 提案本文は1行に主張・引用・帰結を詰め込まず、
  **親の箇条書き=ノート自身の主張・タブ1つ下げた子=文献の引用[[リンク]]や帰結**に構造化する。チェックボックスは1行1個。
  さらに**リンク先を読めば分かる定義・手順・列挙は再掲しない／同じ文献箇所を複数ノートで繰り返し引用しない／
  双方向リンクを目的にしない／原典が扱っていない主題に原典を接続しない／未決は断定せず「未定。候補は◯◯」と書く**。
  実例は vault `_Reports/review-bundles/2026-08-02_permanent-links/views/バッチ2-…`（適用済み）。
  複数行の提案を生成する種目（draft/merge/spawn）ではこの形を必須とする。

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

- [ ] **Robots 拡張プランの残り判定**: vault 側 `_Reports/review-bundles/2026-08-03_robots-gardener-plan/views/review.md`。
  **Q1 は回答済み（2026-08-03・確認後に書き込み）。Q5 も推奨どおりで実装済み。** 残るのは
  Q2=起草の頭脳の呼び出し方 / Q3=優先順 / Q4=シート置き場。いずれも R6 まで実装が進む前に決めればよい。
  較正資産: 大掃除の統合是非25件を `eval/cleanup_gold_20260802.json` に gold 化済み（R6 アトミック性判定の再現テスト用）。
- [ ] **レビューバンドル判定待ち**: `docs/review-bundles/2026-07-07_mbp-onboarding/views/review.md`（RP 5 個・想定 5 分）。
  MBP 移設＋オンボーディングの構成判断の事後承認。✏️/❌ が出たら core を直して view 再派生。
- [ ] **（週次フロー2〜3週運用後）判定モデル実験**: 凍結較正セット35ペアで LLM-jp-4 / DS4（DeepSeek ローカル）/ Claude gold の三つ巴比較。結果を見て confidence≥5 ゲートの緩和可否を再検討（過剰提案は許容の回答あり 2026-07-11。ただし提案洪水は過去の頓挫要因のためフロー定着を先行）。
  ※ 採否記録の運用方法は決着済み（2026-07-11）: レビューノートのチェックボックス状態を robots が回収して `decisions.jsonl` へ記録。設計正本は `~/pkg_vault/_Reports/2026-07-11 PKG運用改善設計（週次庭仕事フロー）.md`。

## 参照

- 全体感・追記ログ: dev-hub `projects/pkg-robots.md`
- 状態の正本: `README.md`（フェーズ・決着事項）＋このファイル（次の一手）。環境構築の手順は `docs/HANDOFF-MBP.md`（一回性文書）。
