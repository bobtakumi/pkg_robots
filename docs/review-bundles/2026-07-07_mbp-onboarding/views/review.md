# review — MBP 移設完了＋dev-hub オンボーディング（2026-07-07）

_core: [`../core.md`](../core.md)（as_of: pkg_robots `ad9a297`）。本 view は core からの派生。修正依頼は core を直してから再派生する。_

## 30秒サマリー

MBP のセットアップ（HANDOFF-MBP §3.1–3.5）は**全ステップ成功・judge 回帰は Neo 基準と一致**（gold 17/20・非gold link 11/15）。
その後 `/onboard-project` で pkg_robots を dev-hub 管理下に載せた（HANDOFF 常設ボード・CLAUDE.md import・settings・review-bundle 配布、BOARD/projects の実態同期）。
**判断が必要な点は 5 個**。いずれもオンボーディング時の構成判断で、コード・判定ロジックへの変更はゼロ。

## 判断が必要な点（RP）

| # | 問い | 背景 | 推奨 | 却下時 |
|---|------|------|------|--------|
| RP1 | `docs/HANDOFF-MBP.md` は常設 `HANDOFF.md` と併存でよいか | 元タスクは「統合するか検討」。§3/§4 は再セットアップ時に再利用価値あり。役割分担は CLAUDE.md に明記済み | 併存（現状） | §4 を CLAUDE.md へ完全吸収し縮約 or 00-START-HERE へ吸収して削除 |
| RP2 | Neo の初手 = `garden stats`＋安定 ID 実装でよいか | Neo 欄の不変条件を満たす、オフライン実装可の M5 残タスク | このまま | judge precision 追い込みへ差し替え（README は運用後を推奨） |
| RP3 | MBP の初手 = M5 初回本番（judge --limit 40）でよいか | 1件数秒〜十数秒×40、稀に Timeout | limit 40 で実行 | 試運転として --limit 10–20 に下げる |
| RP4 | remote 方針の pkg_robots 部分を「GitHub private で決着」としてよいか | 実態は移行済み（`git remote -v`・fd1ed7c）。判断の事後承認 | 決着承認 | 保留へ戻し自己ホスト bare を第2 remote に再併設 |
| RP5 | review-bundle skill の配布は妥当か | 「レビュードキュメント作成」指示を配布の意思表示と解釈 | 承認（本バンドルが初適用） | skill 削除＋配布先記録から除去 |

依存関係: なし（各 RP は独立に判定可）。

## 確認のみ（判断不要）

- MBP セットアップ全 pass・回帰 Neo 基準一致（実測）。Ollama/bge-m3-8k は導入済みだった。
- BOARD レジストリ・インフラ健全性・hub HANDOFF・配布先記録を実態へ同期。
- 判定ロジック・較正セット・config への変更は一切なし。

## リスク要点

- confidence≥5 ゲートが提案品質の生命線（閾値を下げない）。
- CLAUDE.md 要点は HANDOFF-MBP §4 の要約 — §4 改訂時は同期が必要。
- M5 初回実行は DGX llama-server 稼働が前提・時間がかかる。

## レビュー後の流れ

✅ なら: MBP で M5 初回本番実行（RP3 の判定に従う）→ 初回レポートを週末レビュー → `data/decisions.jsonl` の運用方法を決める（HANDOFF 保留欄）。
✏️/❌ なら: core を修正 → 本 view を再派生 → changelog に追記。

## 判定返却テンプレ

```
全 RP 一括 ✅（下の個別判定は不要）

RP1: ✅ / ✏️ / ❌ — コメント:
RP2: ✅ / ✏️ / ❌ — コメント:
RP3: ✅ / ✏️ / ❌ — コメント:
RP4: ✅ / ✏️ / ❌ — コメント:
RP5: ✅ / ✏️ / ❌ — コメント:
```
