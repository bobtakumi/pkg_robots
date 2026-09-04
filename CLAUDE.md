# pkg_robots — プロジェクト指示（Claude Code が起動時に自動読込）

@../dev-hub/CLAUDE.md

このファイルは Claude Code が起動時に必ず読む。上の import で dev-hub の恒久ルール
（日本語応答・git 同期層が大元・二重持ち禁止 等）を自動で取り込み、下の `@HANDOFF.md` で
**現在の引き継ぎ（次の一手）** を repo から取り込む（ローカルのメモリ機構 `~/.claude/...` は
別環境へ渡らないため、引き継ぎは repo 内ファイルに置く）。

## 起動時にやること

1. **まず `HANDOFF.md` の「いまの環境の欄」を確認する。** 内容があれば最初にユーザーへ要約提示し、
   その作業から着手する（または不明点を仰ぐ）。
2. **pull 済みかを 2 つの repo について確認する**: この repo（`git pull`＝HANDOFF の最新化）と
   `~/dev-hub`（`git -C ~/dev-hub pull`＝hub ルール・skill の最新化）。未 pull なら先に取り込む。
3. `~/dev-hub` が参照可能か意識する（この repo の `.claude/settings.json` の
   `additionalDirectories: ["../dev-hub"]` で常時付与されるのが標準。読めない場合は
   設定の欠落なので、テンプレ `templates/PROJECT_SETTINGS_TEMPLATE.json` からの導入をユーザーへ提案する）。

## 引き継ぎの更新規律（セッションを終える側）

- `HANDOFF.md` は**環境別欄の常設ボード＝次の一手の大元**。終わる前に各欄を実状態へ更新する
  （「何を・どう確認するか」まで書く。済んだ項目は消す）。
- **不変条件: 持ち運び端末（Neo 等）の欄を絶やさない。**
- 引き継ぎは**コミットして渡す**（push まで）。受け手は別環境で pull → 起動 → 自動読込で続きに入れる。

@HANDOFF.md

## このリポジトリの要点

- **Vault（`~/pkg_vault`）へは read + propose**。無条件に書けるのは `_Reports/garden-weekly-YYYYMMDD.md`（judgment sheet・`garden sheet`）と旧 `_Reports/suggest-YYYYMMDD.md`（`garden report`・移行済み）のみ。
  加えて **`2_Permanent/` へは `garden apply` 経由でのみ書ける**（2026-08-03 Q1 回答）。条件は「人間がシートで採用/編集と判定した提案であること」「before が現在の本文と一字一致すること」「Obsidian が起動していないこと」の3つで、いずれかを欠いたら書かずに差し戻す。それ以外の経路・パスは読むだけ。
- 全体像・経緯・落とし穴は `docs/00-START-HERE.md`。次の一手の大元はこの repo の `HANDOFF.md`。
  環境構築の一回性の手順書は 2026-09-05 に削除した（判定 = 一回性のセットアップ記録は git が持つ）。
  再構築が要るときは `git log --diff-filter=D -- docs/HANDOFF-MBP.md` で最後の版を引く。
- **judge まわりの触ってはいけないもの**（この 4 つがこの repo での大元。根拠の実測は `docs/M6-回帰結果-LLMjp4.md`）:
  - `[report] min_confidence`（confidence≥5 ゲート）を安易に下げない — LLM-jp-4 の過剰リンク対策。提案洪水は過去の頓挫要因。
  - judge に `response_format: json_object` を送らない — DGX の llama.cpp は 400 になる。プロンプト強制＋パースリトライ実装（`judge_pair`）を触らない。
  - `call_llm` に max_tokens を送らない — thinking モデルは推論で打ち切られ content が空になる。
  - evidence 逐語検証（幻覚ガード）を緩めない — 妥当率を上げたいからと検証を弱めるのは over-fit。
- `data/`（garden.db 等）は git 管理外のビルド成果物。各マシンで `.venv/bin/python -m garden index` で再生成する。
- 較正セット（`eval/calibration_export.json`＋`calibration_labels.jsonl`）は凍結。モデル差し替え時の回帰テスト専用。

## 判定文書（レビューバンドル）

方式の大元は dev-hub `methodology/review-bundle/`（`SKILL.md` を手順書として読む。複製は置かない — 2026-09-02 に複製配布を廃止）。この節が持つのは、この repo 固有の作法だけ。**書けるのは hub の規約への追加**で、規約そのものを覆す形は書かない。

- 置き場: `review-bundles/<date>_<topic>/`（2026-09-02 に `docs/` 配下から移した）。**vault 側の提案・庭仕事に関する判定は vault の `_Reports/review-bundles/` に置く**（vault 側の規律が大元）
- 判定が済んだら、要点を `HANDOFF.md` と `README.md` へ書いてから束を削除する
