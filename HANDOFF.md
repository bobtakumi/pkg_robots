# HANDOFF — pkg_robots（環境別欄の常設ボード）

_`CLAUDE.md` から自動読込される**次の一手の大元**（dev-hub 側 `projects/pkg-robots.md` は状態をコピーしない）。
セッションを終える側は各欄を実状態へ更新し、**持ち運び端末（Neo 等オフライン可の環境）の欄を絶やさず**
commit & push する（不変条件）。環境構築の一回性の手順書は 2026-09-05 に削除した — 要るときは `git log --diff-filter=D -- docs/HANDOFF-MBP.md` で引く。_

## Neo（Mac・GPU なし・オフライン可）

- [ ] **次段 = PKG Hermes Robot（2026-08-23 ユーザー判定）**: Hermes Agent を判定・庭仕事の実行役に据える版。別 repo を作らず同じ repo の次の段として進める。**先に週次サイクルの初回本番を通す**（下の MBP 欄）。
- [ ] **残りの実装**: R7（launchd 週次自動化・`stats` の種目別拡張）と R6（高性能LLM proposer。Q2 の回答待ち）。
  R7 は MBP 常時稼働が前提なので、先に MBP 復帰が要る。
  体裁の確定仕様（2026-08-03 ユーザー指示 + バッチ2 の返却）: 提案本文は1行に主張・引用・帰結を詰め込まず、
  **親の箇条書き=ノート自身の主張・タブ1つ下げた子=文献の引用[[リンク]]や帰結**に構造化する。チェックボックスは1行1個。
  さらに**リンク先を読めば分かる定義・手順・列挙は再掲しない／同じ文献箇所を複数ノートで繰り返し引用しない／
  双方向リンクを目的にしない／原典が扱っていない主題に原典を接続しない／未決は断定せず「未定。候補は◯◯」と書く**。
  実例は vault `_Reports/review-bundles/2026-08-02_permanent-links/views/バッチ2-…`（適用済み）。
  複数行の提案を生成する種目（draft/merge/spawn）ではこの形を必須とする。

## MBP（M3 Max・埋め込みホスト・robot 本体）

- [ ] **週次サイクルの初回本番 — シートは生成済み。あとは記入と回収**（2026-08-24）:
  - 記入するもの = `~/pkg_vault/_Reports/garden-weekly-20260824.md`（提案 5 件 = 成熟度 4・Zettel 間リンク 1。各件の末尾で採用か却下にチェックを 1 つ）
  - 回収 = `.venv/bin/python -m garden collect ~/pkg_vault/_Reports/garden-weekly-20260824.md`（`--dry-run` で内訳だけ見られる）
  - 反映 = `.venv/bin/python -m garden apply --write --commit`（Obsidian を閉じてから）
  - ⚠ **文献リンクの提案が 1 件も載っていない**。判定役（Spark）へ繋げず判定を回せていないため（下記）。規則ベースと Zettel 間リンクだけのシートになっている
- [ ] **判定役へ繋がるようにする（ローカルネットワークの許可）**: `garden judge` が Spark へ繋がらない。
  相手は生きていて `curl`・`nc` では通るのに、**Python からだけ「No route to host」で落ちる**。
  2026-08-24 の切り分け: 同じ宛先へ `/usr/bin/python3` は繋がり、`.venv`（uv が入れた Python）は繋がらない。
  同じ Python でも `localhost` は繋がる。＝ macOS のローカルネットワークの許可がこの Python に無い。
  対処は 2 つあり、**Tailscale 経路への切り替えのほうがユーザーの操作を要らない**（2026-08-25 の hub 側の棚卸しで結論）。
  ① `config.toml` の `[judge] endpoint` を Tailscale の IP（`http://100.117.133.28:11434/v1`）へ変える。
     LAN 名（`spark-062c.local`）はローカルネットワークの許可に掛かるので、Neo からも使わない。
  ② 通らなければ システム設定 → プライバシーとセキュリティ → ローカルネットワーク で、実行しているターミナルを許可する。
  許可が通ったら `candidates`（済・3,677 ペア）→ `judge --limit 40` → `sheet` の順で回すと文献リンクが載る。

- [ ] **稼働・疎通の事前チェック**（2026-07-11 時点で MBP は Tailscale 上オフライン＝まず復帰。レポート再設計の実装とは独立に進められる）:
  ① MBP をネットワーク復帰させ、Tailscale で bobmbp が active になること（スリープ／Tailscale 停止／省電力設定を疑う。週次自動実行はこれの常時成立が前提）。
  ② vault 同期: **2026-08-25 の実測で未 push は 0 件**（2026-08-23 に MBP が tailnet へ復帰して解消済み。以前は 80 件超が滞留していた）。着手時にもう一度 `git -C ~/pkg_vault log --branches --not --remotes --oneline | wc -l` で見る。
  ※ この欄の実測値（notes 数・回帰基準等）は 2026-07-11 時点のもの。**着手時にまず洗い替えてから照合する**（R1〜R5 実装後の再計測はしていない）。
  ③ MBP で `~/pkg_robots` と `~/dev-hub` を `git pull`（本引き継ぎと実装メモを取得）。
  ④ DGX 到達: `curl -s --max-time 6 http://spark-062c.local:11434/v1/models` がモデルを返す。⑤ Ollama 常駐＋`bge-m3-8k` が存在。
  ⑥ vault 同期後に `python -m garden index` を再実行。期待値は notes 780 前後（従来 796 から 2026-07-11 の整合性掃討で PMPP スタブ16件が削除済み）・zettel 124・chunks 全埋め込み。
  大きくズレたら `judge --regress` で基準（JSON妥当 29/35・gold 17/20・非gold link 11/15）からの悪化を確認。
  ※ Neo クローンの `data/` はプロト由来で本番 `findings.json` 未生成。本番サイクルは MBP 側で回す。
- [ ] **M5 週次サイクルの初回本番実行**（レポート再設計の実装後は新体裁で）:
  `candidates` → `judge --limit 40` → `sheet`（旧 `report` は移行済み・週次は sheet を使う）。週末レビュー後は `collect <シートパス>` → `stats` で採否を回収・集計。
  確認: `~/pkg_vault/_Reports/` に週次ノートが生成され、上位5件が confidence≥5 でゲートされていること。実行後 vault 側を commit/push。
  ※ 環境構築は 2026-07-07 完了済み — index 再構築（notes 796・chunks 2589 全埋め込み）、judge 回帰が Neo 基準一致（gold 17/20・非gold link 11/15・JSON妥当 30/35）。
- [ ] **週次自動実行のセットアップ**（初回本番実行の後）: launchd で毎週決まった曜日に `candidates → judge → report` を自動実行し、レビューノートが人手なしで生える状態にする（MBP 常時稼働前提・2026-07-11 設計判断）。
  確認: 指定曜日に週次ノートが自動生成される。

## Spark（DGX・GPU 実行）

- [ ] なし（llama-server で LLM-jp-4 を提供し続けるのみ。疎通確認: `curl http://spark-062c.local:11434/v1/models`）。

## 保留・意思決定待ち（ユーザー入力が要るもの）

- [ ] **Robots 拡張プランの残り判定**: vault 側 `_Reports/review-bundles/2026-08-03_robots-gardener-plan/views/review.md`。
  **Q1 は回答済み（2026-08-03・確認後に書き込み）。Q5 も推奨どおりで実装済み。**
  Q3（優先順）と Q4（シート置き場）は 2026-08-03 の残件バンドルで「確認のみ」に降ろした＝推奨どおりで進める。
  残る判断は **Q2=起草の頭脳の呼び出し方**（(a) 人間が Claude Code セッションを起こす／(b) `claude -p` ヘッドレス／
  (c) API 直叩き。推奨は当面 (a)）。R6 に着手する前に決めればよい。
  → 判断点は vault 側 `_Reports/review-bundles/2026-08-03_residual-items/views/review.md` の「判断6」に集約した。
  較正資産: 大掃除の統合是非25件を `eval/cleanup_gold_20260802.json` に gold 化済み（R6 アトミック性判定の再現テスト用）。
- [ ] **レビューバンドル判定待ち**: `review-bundles/2026-07-07_mbp-onboarding/views/review.md`（RP 5 個・想定 5 分）。
  MBP 移設＋オンボーディングの構成判断の事後承認。✏️/❌ が出たら core を直して view 再派生。
- [ ] **（週次フロー2〜3週運用後）判定モデル実験**: 凍結較正セット35ペアで LLM-jp-4 / DS4（DeepSeek ローカル）/ Claude gold の三つ巴比較。結果を見て confidence≥5 ゲートの緩和可否を再検討（過剰提案は許容の回答あり 2026-07-11。ただし提案洪水は過去の頓挫要因のためフロー定着を先行）。
  ※ 採否記録の運用方法は決着済み（2026-07-11）: レビューノートのチェックボックス状態を robots が回収して `decisions.jsonl` へ記録。設計の大元は `~/pkg_vault/_Reports/2026-07-11 PKG運用改善設計（週次庭仕事フロー）.md`。

## 参照

- 全体感・追記ログ: dev-hub `projects/pkg-robots.md`
- 状態の大元: `README.md`（フェーズ・決着事項）＋このファイル（次の一手）。
