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
    p_rep = sub.add_parser("report", help="提案レポートを Vault の _Reports/ に生成（M4）")
    p_rep.add_argument("--input", help="findings ファイル（省略時 data/findings.json）")
    p_rep.add_argument("--judge-note", default="config の judge モデル", help="レポートに記す判定者")
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


main()
