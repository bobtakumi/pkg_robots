# core — MBP 移設完了＋dev-hub オンボーディング（2026-07-07）

- title: MBP 移設（O11）完了と dev-hub 管理下へのオンボーディングのレビュー
- date: 2026-07-07
- status: レビュー待ち
- 対象一覧:
  - `~/pkg_robots`: `CLAUDE.md`（新設）・`HANDOFF.md`（新設）・`.claude/settings.json`（新設）・`.claude/skills/review-bundle/SKILL.md`（配布）・`README.md` 状態欄
  - `~/dev-hub`: `BOARD.md`（レジストリ行・インフラ健全性・更新日）・`projects/pkg-robots.md`（remote・正本・追記ログ）・`HANDOFF.md`（タスク消化・保留更新）・`methodology/review-bundle/README.md`（配布先記録）
- as_of: pkg_robots `ad9a297`（dev-hub 側は本バンドル commit と同時に push）
- changelog:
  - 2026-07-07: 初版

## findings（実施したこと）

- 🟦確定 **MBP セットアップ（HANDOFF-MBP §3.1–3.5）全ステップ成功**。DGX 到達（ping 4ms・/v1/models が LLM-jp-4 を返却）、vault パス `/Users/bobtk/pkg_vault` 一致、venv+numpy 2.5.1、`garden index` が期待値どおり（notes 796・chunks 2589 全埋め込み・zettel 124/被リンク0 31）。source_refs: `docs/HANDOFF-MBP.md` §3、`README.md` 状態欄
- 🟦確定 **judge 回帰が Neo 実測基準と一致**: gold一致 17/20・非gold link 11/15（完全一致）、JSON妥当 30/35（基準 29/35 を僅かに上回る）。invalid 5 件は全て evidence 逐語検証失敗＝幻覚ガードの正常動作。source_refs: `data/findings_regress.json`（git 外・MBP ローカル）、`docs/HANDOFF-MBP.md` §3.5
- 🟦確定 Ollama＋`bge-m3-8k` は MBP に**導入済みだった**（2026-07-06 作成・brew services 常駐）。再作成せず埋め込み API の実測（1024 次元）のみで確認。
- 🟦確定 remote は GitHub（`https://github.com/bobtakumi/pkg_robots.git`）に移行済みだった（`git remote -v` 実測・commit fd1ed7c の §5 修正と整合）。BOARD・projects ページの「自己ホスト（Tailscale）」記述を実態へ更新。source_refs: `dev-hub/BOARD.md` レジストリ行、`dev-hub/projects/pkg-robots.md`
- 🟨推測（確定扱いで実施） 機密度は BOARD インフラ健全性の「GitHub リポジトリは全て private 運用」に合致するため、ユーザー確認なしで private 前提の記述にした。

## open_points（判断が必要な点）

### RP1: docs/HANDOFF-MBP.md の扱い — 常設 HANDOFF.md と併存でよいか
- 問い: 一回性のセットアップ文書 `docs/HANDOFF-MBP.md` を存置し、新設の常設ボード `HANDOFF.md` から参照する構成でよいか。
- 背景: hub HANDOFF の元タスクは「発展統合するか**検討して**導入」だった。§3（環境構築手順）と §4（注意点）は再セットアップ時に再利用価値があるため、吸収・削除ではなく併存を選んだ。役割分担（HANDOFF-MBP=一回性手順／HANDOFF.md=次の一手の正本）は repo `CLAUDE.md` に明記済み。
- 推奨: 併存（現状）。
- 却下時: §4 注意点を `CLAUDE.md` 要点へ完全吸収し、HANDOFF-MBP は §3 手順のみに縮約（または docs/00-START-HERE.md へ吸収して削除）。いずれも既存ファイルで受け皿は実在。

### RP2: Neo 欄の初手 = M5 未実装 2 点（garden stats・安定 ID）でよいか
- 問い: 持ち運び端末 Neo の次の一手を「`garden stats`（採用率集計）＋提案への安定 ID 付与の実装」としたが妥当か。
- 背景: 不変条件（Neo 欄を絶やさない）を満たすため、オフラインで実装可能・実 LLM 不要な M5 残タスク（README 残タスク節に記載）を選んだ。
- 推奨: このまま。
- 却下時: README 残タスク節の別項目「judge の precision 追い込み（プロンプト調整）」へ差し替え（ただし README 自身が「運用を回してから調整する方が費用対効果が良い」と記す）。

### RP3: MBP 欄の初手 = M5 週次サイクル初回本番実行でよいか
- 問い: `candidates` → `judge --limit 40` → `report` の一気通し（HANDOFF-MBP §3.6）を MBP の次の一手としたが、初回から limit 40 で実行してよいか。
- 背景: 判定は thinking モデルで 1 件数秒〜十数秒・稀に Timeout（既知）。40 件で最長 10 分超の見込み。
- 推奨: limit 40 で実行（Neo 時代の実績値）。
- 却下時: `--limit` を 10–20 に下げた試運転を挟む（CLI オプションとして実在）。

### RP4: hub 保留「remote 方針」の pkg_robots 部分を決着扱いにした
- 問い: hub `HANDOFF.md` の保留項目から pkg_robots を外し「GitHub private へ移行済み＝決着」と記したが承認するか。
- 背景: `git remote -v` の実態と HANDOFF-MBP §5 の記述（GitHub 方式へ修正済み・commit fd1ed7c）に基づく。ただし「自己ホストと併設するか」の判断自体はユーザーのものだったため、事後承認を求める。
- 推奨: 決着承認（GitHub private 単独運用）。
- 却下時: 保留へ戻し、自己ホスト bare repo（`~/git/pkg-robots.git`）を第2 remote として再併設（旧方式のインフラは bobmbp に実在）。

### RP5: review-bundle skill の pkg_robots への配布
- 問い: 配布 skill として review-bundle を `.claude/skills/review-bundle/` へ複製し、正本側 README に配布先を記録したが妥当か。
- 背景: onboarding 手順 5 は「どれを配るか迷ったらユーザーに確認」。本セッション中の指示「レビュードキュメントも作成」を配布の意思表示と解釈して実施した。
- 推奨: 承認（本バンドル自体が初回実適用）。
- 却下時: `.claude/skills/review-bundle/` を削除し、正本 README の配布先記録から pkg_robots を除去（レビューは hub の SKILL.md を手順書として読む方式に戻る）。

## confirmations（確認のみ・判断不要）

- 🟦 BOARD レジストリ行のフォーカスを「M5 週次運用ロールアウト（MBP 移設完了 2026-07-07）」に更新、repo 欄を GitHub private に更新。
- 🟦 BOARD インフラ健全性: HANDOFF 常設ボード・import とも「pkg_robots: 導入済み（2026-07-07）」へ更新。
- 🟦 hub HANDOFF の Neo タスク「pkg_robots へ handoff 雛形を導入」を消化（削除）。
- 🟦 `.claude/settings.json` はテンプレそのまま（既存 settings なし・マージ不要だった）。
- 🟦 `data/` は git 管理外のまま（各マシンで `garden index` 再生成方式・変更なし）。
- 🟦 較正セットは凍結のまま・判定ロジックへの変更は一切なし（本セッションは環境構築と文書のみ）。

## risks（リスク・注意）

- 🟦 LLM-jp-4 の過剰リンク傾向（非gold 11/15）は **confidence≥5 ゲート前提**で実用水準。閾値を下げると提案洪水（過去の頓挫要因）。ガードは `CLAUDE.md` 要点に焼き込み済み。
- 🟨 `CLAUDE.md` の「触ってはいけないもの」は HANDOFF-MBP §4 の要約＝軽微な二重持ち。dev-hub 運用「恒久ルールは CLAUDE.md へ」に従った意図的な焼き込みだが、§4 改訂時は CLAUDE.md too の同期が必要。
- 🟦 M5 初回実行は時間がかかる（judge 40 件・稀に Timeout）。DGX 側 llama-server の稼働が前提（疎通: `curl http://spark-062c.local:11434/v1/models`）。
