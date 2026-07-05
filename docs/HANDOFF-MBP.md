# 引き継ぎ: pkg_robots を MBP で稼働させる（MBP の Claude Code 向け）

> **この文書の読者は MBP（bobmbp・M3 Max・128GB）上の Claude Code** です。
> Neo（作業機）で M0–M4 実装・M6 判定側の接続確認まで終えた pkg_robots を、
> MBP へ移して**埋め込みホスト兼 robot 本体**として動かすのが目的です。
> まずこの文書を通読し、§3 の手順を上から実行してください。不明点は憶測で埋めず、人間に確認を。

---

## 1. pkg_robots とは / 現在地

**Connector robot** = Obsidian の Personal Knowledge Garden（`~/pkg_vault`）に対し、
「zettel（自分の考え）」と「文献ノート（読んだ内容）」の間の潜在的なリンク候補を LLM に判定させ、
週次で提案レポート `_Reports/suggest-YYYYMMDD.md` を出すツール。**Vault へは read + propose**（提案レポート以外は書かない）。

4段パイプライン `garden index → candidates → judge → report`。実装状況:

| 段 | 役割 | 状態 |
|---|---|---|
| index | vault を走査し埋め込み・リンクグラフ・統計を SQLite に構築 | 実装済み。**MBP で再実行が必要**（`data/` は git 管理外のため引き継がれない） |
| candidates | 埋め込み類似で層跨ぎ（zettel×文献）候補を機械生成 | 実装済み・O2 決着（bge-m3-8k, recall@30=63.8%） |
| judge | 候補を LLM-jp-4（DGX）で判定。JSON＋evidence 逐語検証＋パースリトライ | 実装済み・M6 判定側接続確認済み |
| report | confidence≥5 でゲートし上位5件を提案レポート化 | 実装済み |

**Phase 1 は実質完成。残りは「この MBP で実際に運用を回す」こと**（＝この引き継ぎの目的）。

## 2. アーキテクチャ（3マシン構成）

- **DGX Spark** = 判定 LLM。`spark-062c.local:11434/v1`（llama.cpp llama-server・**認証なし**・OpenAI 互換）、
  モデル `llm-jp-4-32b-a3b-thinking-Q4_K_M.gguf`。既存アプリ bobook が同じものを使用中。
- **MBP（このマシン）** = 埋め込みホスト（Ollama + bge-m3-8k）＋ pkg_robots 本体。
- **Neo** = 作業・チャット元。vault は Neo↔MBP を **MBP 上のベアリポジトリ（`~/git/`）経由で同期**（GitHub ではない）。

→ judge は DGX へ、embed は MBP localhost へ。config.toml は既にこの前提で設定済み。

## 3. セットアップ手順（上から順に）

### 3.1 前提確認
```sh
# vault の場所（config.toml の vault.path と一致すること。MBP でも /Users/bobtk/pkg_vault のはず）
ls ~/pkg_vault/1_Literature >/dev/null && echo "vault OK"
# DGX への到達（LAN。認証なしで models が返る）
curl -s --max-time 6 http://spark-062c.local:11434/v1/models | head -c 200; echo
```
vault パスが違う場合は `config.toml` の `[vault].path` を実際の場所に直す。

### 3.2 Python 環境
```sh
cd ~/pkg_robots            # clone 直後の場所（§5 参照）
python3 -m venv .venv
.venv/bin/pip install numpy
```
`garden index` は標準ライブラリのみ、`candidates` 以降は numpy を使う。

### 3.3 埋め込みモデル（Ollama + bge-m3-8k）
```sh
brew install ollama 2>/dev/null; brew services start ollama   # 常駐化（Neo では起動プロセス巻き添え死を避けるため services 化した）
ollama pull bge-m3
ollama create bge-m3-8k -f Modelfile.bge-m3-8k                 # num_ctx 8192 を焼いた派生（リポジトリ同梱）
```
> なぜ bge-m3-8k か: 日本語+markdown はトークン膨張が激しく、素の bge-m3 は 8192tok 上限に当たる。
> Modelfile で num_ctx を明示。それでも超過するチャンクは index 側がクライアントで段階切り詰めする。

### 3.4 索引の構築（埋め込み込み・数分〜10分）
```sh
.venv/bin/python -m garden index
```
期待出力: `notes: 796 …` / `zettel: 124 / 被リンク0: 31 …`。`data/garden.db` と `data/stats.json` が生成される。

### 3.5 判定の回帰確認（MBP からも DGX に届くかの実証を兼ねる）
```sh
.venv/bin/python -m garden judge --regress eval/calibration_export.json 2>/dev/null
```
較正35ペアを実 LLM-jp-4 で判定し、gold と照合する。**Neo での実測基準**は:
`JSON妥当 29/35・gold一致 17/20・非gold link 11/15`。
大きく外れなければ MBP からの判定経路は正常。数値がひどく悪い場合は §4 の注意点を確認。

### 3.6 パイプライン一気通し（本番の1サイクル）
```sh
.venv/bin/python -m garden candidates          # data/candidates.json（層跨ぎ候補）
.venv/bin/python -m garden judge --limit 40    # data/findings.json（DGX で判定・時間がかかる）
.venv/bin/python -m garden report              # ~/pkg_vault/_Reports/suggest-YYYYMMDD.md
```
最後に vault 側を commit/push すれば Neo に同期され、週末レビューで読める。

## 4. 既知の注意点（運用前に必ず把握）

- **LLM-jp-4 は過剰リンク傾向**（M6 回帰: 無関係ペアの 11/15 を link と誤判定）。
  対策として **report は confidence≥5 でゲート**（config `[report].min_confidence`）。ゲート後の提案品質は良好（実測で上位5件が全て妥当）。
  **この閾値を安易に下げないこと。** 提案洪水は過去の頓挫要因。詳細 `docs/M6-回帰結果-LLMjp4.md`。
- **judge の JSON 強制は不可**。DGX の llama.cpp ビルドは `response_format: json_object` が 400 になる。
  プロンプト側で JSON を強制し、パース/逐語検証失敗はリトライで吸収する実装（`judge_pair`）。触らない。
- **thinking モデルの出力上限は指定しない**。絞ると推論で打ち切られ content が空になる。`call_llm` は max_tokens を送っていない（正しい）。
- **判定は遅い**（thinking モデル・1件数秒〜十数秒、稀に Timeout）。全候補を judge に流さず、`--limit` で絞る。
- **evidence 逐語検証は幻覚ガード**。LLM が引用を言い換えると invalid になるが、これは根拠捏造を弾く正しい挙動。妥当率を上げたいからと検証を緩めないこと（over-fit 注意）。

## 5. このリポジトリの入手（GitHub）

pkg_robots は **GitHub で同期**する（vault は MBP ベアリポジトリ方式だが、このリポジトリは別）。MBP では:
```sh
git clone https://github.com/bobtakumi/pkg-robots.git ~/pkg_robots
cd ~/pkg_robots
```
以後 MBP 側の変更も `git push origin main` で GitHub 経由に共有する。
（remote 構成は §2 の通り。vault と同じ `~/git/*.git` 方式。）

## 6. 残タスク（Phase 1 完了 → 運用/Phase 2）

- **M5 週次運用の定着**: `index → candidates → judge → report` を週次で回し、`decisions.jsonl` に採否を記録
  （スキーマは実装プラン §M5 参照。記入は人間 or 人間指示下の代筆）。採用率が閾値・プロンプト調整の根拠になる。
- **`garden stats`**（採用率集計）と、提案への安定 ID 付与（decisions との突合用）は未実装。M5 で追加。
- **judge の precision 追い込み**（任意）: プロンプトで「無関係なら迷わず skip」を強調すれば素の precision も上がる。
  ただし confゲートで実用水準に達しているので、運用を回してから調整する方が費用対効果が良い。
- **Phase 2**: GraphRAG / Reflector / 草刈りレポート。index が既にマクロ信号（孤立・タグ頻度等）を stats.json に出しているので、そこから着手できる。
- **フェイルオーバー**（任意）: bobook の `resolve_openai_url` に倣い、judge の接続先を LAN→Tailscale で切り替え可能にする。

## 7. 正典ドキュメント（vault 側・Neo と共有）

- プロジェクトノート: `~/pkg_vault/_Reports/2026-07-02 プロジェクトノート Robots in the Garden v4.md`（全体方針・出自タグ・変更履歴）
- 実装プラン: `~/pkg_vault/_Reports/2026-07-02 Robots実装プラン Phase1（インデクサ+Connector）.md`（M0–M6 の詳細・受け入れ基準）
- これらが設計判断の正典。本 HANDOFF と食い違ったら vault 側を優先。
