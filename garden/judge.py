"""garden judge — 候補ペアの LLM 判定（実装プラン M3）。

2モード:
- 通常: config の OpenAI 互換エンドポイントで candidates.json を判定 → data/findings.json
- --validate LABELS EXPORT: 外部で付けた判定（較正時は Claude が judge 役）を
  同一の検証パイプライン（JSON 妥当性・evidence 部分文字列・逐語性）に通す

幻覚ガード: evidence_* は渡したテキストの部分文字列でなければ無効（自動 skip 扱い）。
"""

import json
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

VERDICTS = {"link", "skip"}
RELATIONS = {"根拠", "具体例", "反例", "同型パターン", "発展"}


def load_system_prompt(root: Path) -> str:
    text = (root / "prompts" / "connector_judge.md").read_text(encoding="utf-8")
    m = re.search(r"^## system\n(.*?)(?=^## )", text, re.S | re.M)
    if not m:
        sys.exit("prompts/connector_judge.md に '## system' セクションがない")
    return m.group(1).strip()


def fetch_pair_texts(con: sqlite3.Connection, zettel_path: str, lit_path: str,
                     best_seq: int | None = None):
    """判定材料 = 類似度最上位チャンク + 冒頭チャンク（文脈用）。

    較正 v1 の教訓（cal-18）: 冒頭2チャンクだけ渡すと、候補生成が反応した箇所が
    判定材料に入らず gold を skip してしまう。best_seq を必ず含める。
    """
    z_body = con.execute(
        "SELECT text FROM chunks WHERE note_path = ?", (zettel_path,)).fetchone()
    seqs = sorted({0, best_seq if best_seq is not None else 0})
    chunks = [r[0] for r in con.execute(
        f"SELECT text FROM chunks WHERE note_path = ? AND seq IN ({','.join('?' * len(seqs))}) "
        "ORDER BY seq", (lit_path, *seqs))]
    return (z_body[0] if z_body else ""), chunks


def build_user(pair: dict, zettel_body: str, chunks: list[str]) -> str:
    source = pair["lit_path"].split("/")[1] if "/" in pair["lit_path"] else ""
    parts = [f"## zettel: {pair['zettel_title']}", zettel_body,
             f"\n## 文献ノート: {pair['lit_title']}（{source}）",
             "### 抜粋（類似度最上位チャンク）"]
    parts += chunks
    return "\n".join(parts)


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", "", s)


def validate_one(raw: str, zettel_body: str, chunks: list[str]) -> tuple[dict | None, str]:
    """(判定dict, エラー理由)。判定不能・検証失敗は (None, 理由)。"""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None, "JSONなし"
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None, "JSONパース失敗"
    if d.get("verdict") not in VERDICTS:
        return None, f"verdict不正: {d.get('verdict')}"
    if d["verdict"] == "skip":
        return d, ""
    if d.get("relation") not in RELATIONS:
        return None, f"relation不正: {d.get('relation')}"
    if not isinstance(d.get("confidence"), int) or not 1 <= d["confidence"] <= 5:
        return None, "confidence不正"
    # 逐語性検証（空白差のみ許容）
    if _norm_ws(d.get("evidence_zettel", "")) not in _norm_ws(zettel_body):
        return None, "evidence_zettel が逐語でない"
    lit_all = _norm_ws("\n".join(chunks))
    if _norm_ws(d.get("evidence_lit", "")) not in lit_all:
        return None, "evidence_lit が逐語でない"
    return d, ""


def call_llm(cfg: dict, system: str, user: str) -> str:
    body = {
        "model": cfg["judge"]["model"],
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        cfg["judge"]["endpoint"].rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def judge_pair(cfg: dict, system: str, user: str, zettel_body: str,
               chunks: list[str], retries: int = 2) -> tuple[dict | None, str, str]:
    """1ペアを判定し (判定dict, エラー理由, 最終raw) を返す。

    このビルドの llama-server は response_format(json_object) が 400 で使えないため
    JSON はプロンプト側で強制する。パース/逐語検証に失敗したら再生成でリトライ
    （DGX 側の実測知見: 素の生成で素の JSON が安定して返る。稀な崩れをここで吸収）。
    ネットワーク例外は呼び出し側に投げる。
    """
    err, raw = "", ""
    for _ in range(retries + 1):
        raw = call_llm(cfg, system, user)
        d, err = validate_one(raw, zettel_body, chunks)
        if d is not None:
            return d, "", raw
    return None, err, raw


def summarize(results: list[dict]) -> dict:
    n = len(results)
    links = [r for r in results if r.get("verdict") == "link"]
    invalid = [r for r in results if r.get("invalid")]
    return {"total": n, "link": len(links), "skip": n - len(links) - len(invalid),
            "invalid": len(invalid),
            "json_valid_rate": round((n - len(invalid)) / n, 3) if n else 0}


def run_validate(cfg: dict, labels_file: Path, export_file: Path) -> None:
    """較正モード: 外部判定を検証し、gold 一致率を測る。"""
    root: Path = cfg["_root"]
    export = {p["id"]: p for p in json.loads(export_file.read_text(encoding="utf-8"))}
    results = []
    for line in labels_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        lab = json.loads(line)
        p = export.get(lab["id"])
        if p is None:
            print(f"[warn] export に無い id: {lab['id']}", file=sys.stderr)
            continue
        d, err = validate_one(json.dumps(lab, ensure_ascii=False), p["zettel_body"], p["chunks"])
        rec = {"id": lab["id"], "zettel_title": p["zettel_title"], "lit_title": p["lit_title"],
               "score": p["score"], "gold": p["gold"]}
        if d is None:
            rec.update(invalid=True, error=err)
        else:
            rec.update(d)
        results.append(rec)

    stats = summarize(results)
    gold_pos = [r for r in results if r["gold"]]
    gold_link = [r for r in gold_pos if r.get("verdict") == "link"]
    nongold = [r for r in results if not r["gold"]]
    nongold_link = [r for r in nongold if r.get("verdict") == "link"]
    stats["gold_agreement"] = f"{len(gold_link)}/{len(gold_pos)}"
    stats["nongold_link_rate"] = f"{len(nongold_link)}/{len(nongold)}"

    out = root / "data" / "findings_calibration.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    for r in results:
        if r.get("invalid"):
            print(f"  invalid: {r['id']} {r['error']}")
        if r["gold"] and r.get("verdict") == "skip":
            print(f"  gold なのに skip: {r['zettel_title'][:24]} → {r['lit_title'][:32]}")
    print(f"→ {out.relative_to(root)}")


def run_regress(cfg: dict, export_file: Path) -> None:
    """M6 回帰: 凍結較正セットを実エンドポイント（LLM-jp-4）で判定し gold と照合する。

    Claude 代役時（run_validate）と同じ較正セット・同じ検証を使い、
    妥当率・gold 一致・非gold link 率を比較して本番投入の可否を判断する。
    """
    root: Path = cfg["_root"]
    if not cfg["judge"]["model"]:
        sys.exit("config.toml の [judge].model が未設定")
    system = load_system_prompt(root)
    export = json.loads(export_file.read_text(encoding="utf-8"))
    results = []
    for i, p in enumerate(export):
        user = build_user(p, p["zettel_body"], p["chunks"])
        try:
            d, err, _raw = judge_pair(cfg, system, user, p["zettel_body"], p["chunks"])
        except Exception as e:  # noqa: BLE001 — 1件の失敗で回帰全体を落とさない
            results.append({"id": p["id"], "gold": p["gold"], "invalid": True,
                            "error": f"call失敗: {type(e).__name__}", "zettel_title": p["zettel_title"],
                            "lit_title": p["lit_title"]})
            print(f"[{i+1}/{len(export)}] {p['id']} CALL-FAIL", file=sys.stderr)
            continue
        rec = {"id": p["id"], "gold": p["gold"], "zettel_title": p["zettel_title"],
               "lit_title": p["lit_title"], "score": p["score"]}
        rec.update(d if d else {"invalid": True, "error": err, "raw": _raw[:300]})
        results.append(rec)
        print(f"[{i+1}/{len(export)}] {p['id']} gold={p['gold']} "
              f"→ {(d or {}).get('verdict', 'INVALID')}", file=sys.stderr)

    stats = summarize(results)
    gold_pos = [r for r in results if r["gold"]]
    gold_link = [r for r in gold_pos if r.get("verdict") == "link"]
    nongold = [r for r in results if not r["gold"]]
    nongold_link = [r for r in nongold if r.get("verdict") == "link"]
    stats["gold_agreement"] = f"{len(gold_link)}/{len(gold_pos)}"
    stats["nongold_link_rate"] = f"{len(nongold_link)}/{len(nongold)}"
    stats["model"] = cfg["judge"]["model"]

    out = root / "data" / "findings_regress.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    print("-- Claude 代役時: valid 35/35・gold一致 19/20・非gold link 1/15 --")
    for r in results:
        if r.get("invalid"):
            print(f"  invalid: {r['id']} {r.get('error')}")
        elif r["gold"] and r.get("verdict") == "skip":
            print(f"  gold なのに skip: {r['id']} {r['zettel_title'][:20]} → {r['lit_title'][:28]}")
        elif not r["gold"] and r.get("verdict") == "link":
            print(f"  非gold を link: {r['id']} {r['zettel_title'][:20]} → {r['lit_title'][:28]}（{r.get('reason','')[:40]}）")
    print(f"→ {out.relative_to(root)}")


def run(cfg: dict, limit: int) -> None:
    """通常モード: エンドポイントで判定（LLM-jp-4 / Ollama 等、M6 で本配線）。"""
    root: Path = cfg["_root"]
    if not cfg["judge"]["model"]:
        sys.exit("config.toml の [judge].model が未設定（較正は `judge --validate` を使用）")
    system = load_system_prompt(root)
    pairs = json.loads((root / "data" / "candidates.json").read_text(encoding="utf-8"))[:limit]
    con = sqlite3.connect(root / cfg["index"]["db_path"])
    results = []
    for i, p in enumerate(pairs):
        z_body, chunks = fetch_pair_texts(con, p["zettel_path"], p["lit_path"],
                                          p.get("best_chunk_seq"))
        d, err, raw = judge_pair(cfg, system, build_user(p, z_body, chunks), z_body, chunks)
        rec = dict(p)
        rec.update(d if d else {"invalid": True, "error": err, "raw": raw[:400]})
        results.append(rec)
        print(f"[{i+1}/{len(pairs)}] {p['zettel_title'][:20]} → "
              f"{(d or {}).get('verdict', 'INVALID')}", file=sys.stderr)
    out = root / "data" / "findings.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summarize(results), ensure_ascii=False))
    print(f"→ {out.relative_to(root)}")
