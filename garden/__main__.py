import argparse

from . import config, index


def main() -> None:
    ap = argparse.ArgumentParser(prog="garden", description="PKG robots CLI（実装プラン Phase 1）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_index = sub.add_parser("index", help="Vault を走査して索引・統計を全再構築（M1）")
    p_index.add_argument("--no-embed", action="store_true", help="埋め込みパスを省略")
    p_cand = sub.add_parser("candidates", help="埋め込み類似によるリンク候補生成（M2）")
    p_cand.add_argument("--eval", action="store_true", help="gold_pairs.yaml で recall を測定（O2 ゲート）")
    p_judge = sub.add_parser("judge", help="候補ペアの LLM 判定（M3）")
    p_judge.add_argument("--limit", type=int, default=50, help="判定するペア数（スコア降順）")
    p_judge.add_argument("--validate", nargs=2, metavar=("LABELS", "EXPORT"),
                         help="外部判定（較正時は Claude）を検証パイプラインに通す")
    p_judge.add_argument("--regress", metavar="EXPORT",
                         help="較正セットを実エンドポイントで判定し gold と照合（M6 回帰）")
    p_rep = sub.add_parser("report", help="提案レポートを Vault の _Reports/ に生成（M4・旧体裁）")
    p_rep.add_argument("--input", help="findings ファイル（省略時 data/findings.json）")
    p_rep.add_argument("--judge-note", default="config の judge モデル", help="レポートに記す判定者")
    p_sheet = sub.add_parser("sheet", help="判定シートを生成（R1・週次はこちら）")
    p_sheet.add_argument("--findings", help="findings ファイル（省略時 data/findings.json）")
    p_sheet.add_argument("--out", help="出力先（省略時 Vault の _Reports/garden-weekly-YYYYMMDD.md）")
    p_col = sub.add_parser("collect", help="判定シートのチェックを回収して decisions に記録（R1）")
    p_col.add_argument("sheet", help="判定シートのパス")
    p_col.add_argument("--dry-run", action="store_true", help="書き込まず内訳だけ表示")
    p_lint = sub.add_parser("lint", help="機械照合と庭の健康診断（R2）")
    p_lint.add_argument("--proposals", action="store_true", help="proposals.jsonl の適用前提も検証")
    p_lint.add_argument("--json", action="store_true", help="機械可読で出力")
    p_stats = sub.add_parser("stats", help="採否の集計（全体・種目別の採用率）")
    p_stats.add_argument("--json", action="store_true", help="機械可読で出力")
    args = ap.parse_args()

    cfg = config.load()
    if args.cmd == "index":
        index.run(cfg, do_embed=not args.no_embed)
    elif args.cmd == "candidates":
        from . import candidates
        candidates.run(cfg, do_eval=args.eval)
    elif args.cmd == "judge":
        from pathlib import Path
        from . import judge
        if args.validate:
            judge.run_validate(cfg, Path(args.validate[0]), Path(args.validate[1]))
        elif args.regress:
            judge.run_regress(cfg, Path(args.regress))
        else:
            judge.run(cfg, limit=args.limit)
    elif args.cmd == "report":
        from pathlib import Path
        from . import report
        report.run(cfg, Path(args.input) if args.input else None, judge_note=args.judge_note)
    elif args.cmd == "sheet":
        from pathlib import Path
        from . import sheet
        sheet.run(cfg, Path(args.findings) if args.findings else None,
                  Path(args.out) if args.out else None)
    elif args.cmd == "collect":
        from pathlib import Path
        from . import collect
        collect.run(cfg, Path(args.sheet), dry_run=args.dry_run)
    elif args.cmd == "lint":
        from . import lint
        lint.run(cfg, as_json=args.json, with_proposals=args.proposals)
    elif args.cmd == "stats":
        from . import stats
        stats.run(cfg, as_json=args.json)


main()
