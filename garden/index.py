"""garden index — Vault を走査して SQLite 索引と統計を全再構築する（実装プラン M1）。

冪等・毎回ゼロから再構築。埋め込みのみ content hash でスキップし、
Ollama 未起動時は埋め込みパスを警告付きで省略する。
"""

import hashlib
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
TAG_LINE_RE = re.compile(r"^\s*-\s*[\"']?#?([\w/\-一-龠ぁ-んァ-ヶー]+)[\"']?\s*$")
INLINE_TAG_RE = re.compile(r"(?<![\w/])#([\w/\-一-龠ぁ-んァ-ヶー]+)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def strip_code(body: str) -> str:
    """コードブロックとインラインコードを空白に潰す。

    文献ノートは原典の wikilink 記法・テンプレート変数・TOML のキー名をコード表記で
    引用している（`[[Note two]]` `[[{{title}} (highlights)]]` `[[step-overrides]]` 等）。
    これを実リンクとして数えると未解決リンクが誤検知で埋まる（2026-08-03 に14件中11件が誤検知と判明）。
    """
    out, in_fence = [], False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else INLINE_CODE_RE.sub(" ", line))
    return "\n".join(out)

SCHEMA = """
CREATE TABLE notes (
  path TEXT PRIMARY KEY, title TEXT, layer TEXT, mtime REAL,
  chars INTEGER, tags TEXT, body_hash TEXT);
CREATE TABLE links (
  src TEXT, target_name TEXT, resolved_path TEXT, unresolved INTEGER);
CREATE TABLE chunks (
  id INTEGER PRIMARY KEY, note_path TEXT, seq INTEGER, heading TEXT,
  text TEXT, text_hash TEXT, embedding BLOB, embed_model TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


def classify(rel: str) -> str:
    name = Path(rel).name
    if rel.startswith("2_Permanent/Zettelkasten/"):
        return "zettel"
    if rel.startswith("2_Permanent/MOC/"):
        return "moc"
    if rel.startswith("2_Permanent/"):
        return "permanent_other"
    if rel.startswith("1_Literature/"):
        if name == "_Index.md":
            return "literature_meta"
        return "literature_index" if name.startswith("00 ") else "literature_section"
    if rel.startswith("3_Projects/"):
        return "project"
    return "other"


def split_frontmatter(text: str) -> tuple[str, str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[4:end], text[end + 4:]
    return "", text


def parse_tags(fm: str, body: str) -> list[str]:
    tags: list[str] = []
    in_tags = False
    for line in fm.splitlines():
        if re.match(r"^tags\s*:", line):
            in_tags = True
            rest = line.split(":", 1)[1].strip()
            if rest.startswith("["):
                tags += [t.strip().strip("\"'#") for t in rest.strip("[]").split(",") if t.strip()]
                in_tags = False
            continue
        if in_tags:
            m = TAG_LINE_RE.match(line)
            if m:
                tags.append(m.group(1))
            elif line.strip():
                in_tags = False
    tags += INLINE_TAG_RE.findall(body)
    return sorted(set(t for t in tags if t))


def chunk_note(body: str, max_chars: int) -> list[tuple[str, str]]:
    """(heading, text) のリスト。max_chars 以下なら1チャンク、超過は ## 見出しで分割。"""
    body = body.strip()
    if len(body) <= max_chars:
        return [("", body)]
    parts: list[tuple[str, str]] = []
    current_head, buf = "", []
    for line in body.splitlines():
        if line.startswith("## "):
            if buf:
                parts.append((current_head, "\n".join(buf).strip()))
            current_head, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if buf:
        parts.append((current_head, "\n".join(buf).strip()))
    # 見出し分割後もなお長いものはハード分割
    out: list[tuple[str, str]] = []
    for head, text in parts:
        while len(text) > max_chars:
            out.append((head, text[:max_chars]))
            text = text[max_chars:]
        if text:
            out.append((head, text))
    return [(h, t) for h, t in out if t]


def scan_vault(cfg: dict) -> list[dict]:
    vault = Path(cfg["vault"]["path"])
    prefixes = tuple(cfg["vault"]["exclude_prefixes"])
    fragments = cfg["vault"]["exclude_fragments"]
    notes = []
    for p in sorted(vault.rglob("*.md")):
        rel = p.relative_to(vault).as_posix()
        if rel.startswith(prefixes) or any(f in f"/{rel}" for f in fragments):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm, body = split_frontmatter(text)
        notes.append({
            "path": rel,
            "title": p.stem,
            "layer": classify(rel),
            "mtime": p.stat().st_mtime,
            "chars": len(body),
            "tags": parse_tags(fm, body),
            "body": body,
            "body_hash": hashlib.sha256(body.encode()).hexdigest()[:16],
        })
    return notes


def levenshtein(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def build_stats(notes: list[dict], links: list[tuple]) -> dict:
    by_layer: dict[str, int] = {}
    for n in notes:
        by_layer[n["layer"]] = by_layer.get(n["layer"], 0) + 1
    in_deg: dict[str, int] = {}
    out_deg: dict[str, int] = {}
    for src, _name, resolved, unresolved in links:
        out_deg[src] = out_deg.get(src, 0) + 1
        if resolved:
            in_deg[resolved] = in_deg.get(resolved, 0) + 1
    zettels = [n for n in notes if n["layer"] == "zettel"]
    lit_paths = {n["path"] for n in notes if n["layer"].startswith("literature")}
    cross = [
        (src, resolved) for src, _n, resolved, _u in links
        if resolved in lit_paths and any(z["path"] == src for z in zettels)
    ]
    tag_freq: dict[str, int] = {}
    for n in notes:
        for t in n["tags"]:
            tag_freq[t] = tag_freq.get(t, 0) + 1
    # 編集距離2以下の紛らわしいタグペア（rubric-README §6: tag hygiene 信号）
    tag_names = sorted(tag_freq)
    confusable = [
        [a, b] for i, a in enumerate(tag_names) for b in tag_names[i + 1:]
        if len(a) > 3 and levenshtein(a.lower(), b.lower()) <= 2
    ]
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "notes_by_layer": by_layer,
        "total_links": len(links),
        "unresolved_links": sum(1 for l in links if l[3]),
        "zettel": {
            "count": len(zettels),
            "orphans_no_inlink": sorted(z["path"] for z in zettels if in_deg.get(z["path"], 0) == 0),
            "no_outlink": sorted(z["path"] for z in zettels if out_deg.get(z["path"], 0) == 0),
            "links_to_literature": len(cross),
        },
        "tag_freq": dict(sorted(tag_freq.items(), key=lambda kv: -kv[1])),
        "tags_per_note": {n["path"]: len(n["tags"]) for n in notes if len(n["tags"]) > 3},
        "confusable_tag_pairs": confusable,
    }


def embed_text_for(note: dict, title_by_path: dict[str, str], links: list[tuple]) -> str | None:
    """zettel は痩せ対策で タイトル+本文+発リンク先タイトル を連結（実装プラン M1）。"""
    if note["layer"] == "zettel":
        linked = [title_by_path[r] for s, _n, r, _u in links if s == note["path"] and r in title_by_path]
        parts = [note["title"], note["body"].strip()]
        if linked:
            parts.append("関連: " + "、".join(linked))
        return "\n".join(parts)
    if note["layer"] in ("literature_section", "literature_index"):
        return None  # チャンク側を埋め込む
    return None


def _embed_call(cfg: dict, texts: list[str]) -> list[list[float]]:
    req = urllib.request.Request(
        cfg["embed"]["endpoint"].rstrip("/") + "/api/embed",
        data=json.dumps({"model": cfg["embed"]["model"], "input": texts, "truncate": True}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["embeddings"]


def try_embed(cfg: dict, texts: list[str]) -> list[list[float]] | None:
    """バッチ埋め込み。トークン超過(400)は1件ずつ・段階切り詰めでフォールバック。

    Ollama 0.31 は bge-m3 で truncate/num_ctx を無視するため（実測）、
    超過チャンクはクライアント側で 20% ずつ短縮して再試行する。
    接続不可のみ None（=埋め込みパス全体のスキップ）。
    """
    try:
        return _embed_call(cfg, texts)
    except urllib.error.HTTPError:
        pass  # バッチ内に超過チャンク → 1件ずつ
    except (urllib.error.URLError, OSError):
        return None
    out = []
    for t in texts:
        while True:
            try:
                out.append(_embed_call(cfg, [t])[0])
                break
            except urllib.error.HTTPError:
                if len(t) < 200:
                    raise
                t = t[: int(len(t) * 0.8)]
            except (urllib.error.URLError, OSError):
                return None
    return out


def run(cfg: dict, do_embed: bool) -> None:
    root: Path = cfg["_root"]
    db_path = root / cfg["index"]["db_path"]
    db_path.parent.mkdir(exist_ok=True)

    notes = scan_vault(cfg)
    title_map: dict[str, str] = {}
    for n in notes:  # basename → path（重複時は先勝ち・zettel/文献優先は不要規模）
        title_map.setdefault(n["title"], n["path"])
    links = []
    for n in notes:
        for m in WIKILINK_RE.finditer(strip_code(n["body"])):
            name = m.group(1).strip().split("/")[-1]
            resolved = title_map.get(name)
            links.append((n["path"], name, resolved, 0 if resolved else 1))

    # 既存 db から埋め込みを text_hash + モデル一致で引き継ぐ（再実行の高速化）
    embed_cache: dict[str, bytes] = {}
    if db_path.exists():
        old = sqlite3.connect(db_path)
        try:
            embed_cache = {
                h: e for h, e in old.execute(
                    "SELECT text_hash, embedding FROM chunks "
                    "WHERE embedding IS NOT NULL AND embed_model = ?",
                    (cfg["embed"]["model"],))
            }
        except sqlite3.OperationalError:
            pass  # スキーマ旧版なら捨てる
        old.close()

    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    con.executemany(
        "INSERT INTO notes VALUES (?,?,?,?,?,?,?)",
        [(n["path"], n["title"], n["layer"], n["mtime"], n["chars"],
          json.dumps(n["tags"], ensure_ascii=False), n["body_hash"]) for n in notes],
    )
    con.executemany("INSERT INTO links VALUES (?,?,?,?)", links)

    title_by_path = {n["path"]: n["title"] for n in notes}
    max_chars = cfg["index"]["chunk_max_chars"]
    chunk_rows = []
    for n in notes:
        if n["layer"] == "zettel":
            text = embed_text_for(n, title_by_path, links)
            chunk_rows.append((n["path"], 0, "", text))
        elif n["layer"] in ("literature_section", "literature_index"):
            for seq, (head, text) in enumerate(chunk_note(n["body"], max_chars)):
                chunk_rows.append((n["path"], seq, head, f"{n['title']}\n{text}"))
    con.executemany(
        "INSERT INTO chunks (note_path, seq, heading, text, text_hash) VALUES (?,?,?,?,?)",
        [(p, s, h, t, hashlib.sha256(t.encode()).hexdigest()[:16]) for p, s, h, t in chunk_rows],
    )

    embedded = 0
    if embed_cache:
        cached = con.executemany(
            "UPDATE chunks SET embedding = ?, embed_model = ? WHERE text_hash = ?",
            [(e, cfg["embed"]["model"], h) for h, e in embed_cache.items()],
        ).rowcount
        embedded += max(cached, 0)
    if do_embed:
        cur = con.execute(
            """SELECT c.id, c.text, n.layer FROM chunks c JOIN notes n ON n.path = c.note_path
               WHERE c.embedding IS NULL ORDER BY c.id""")
        rows = cur.fetchall()
        # 非対称埋め込みモデル用 prefix（ruri 等）。API 送信時のみ付与し、格納テキストと
        # text_hash は raw のまま（∴ prefix を変えたら同一モデルでも要・全再埋め込み）
        qp = cfg["embed"].get("query_prefix", "")
        pp = cfg["embed"].get("passage_prefix", "")
        batch = 32
        for i in range(0, len(rows), batch):
            part = rows[i:i + batch]
            ids = [r[0] for r in part]
            vecs = try_embed(cfg, [(qp if r[2] == "zettel" else pp) + r[1] for r in part])
            if vecs is None:
                print(f"[warn] 埋め込みエンドポイント {cfg['embed']['endpoint']} に接続できず。"
                      f"埋め込みパスをスキップ（{embedded}/{len(rows)} 済）", file=sys.stderr)
                break
            for cid, v in zip(ids, vecs):
                con.execute("UPDATE chunks SET embedding=?, embed_model=? WHERE id=?",
                            (json.dumps(v), cfg["embed"]["model"], cid))
            embedded += len(ids)

    stats = build_stats(notes, links)
    stats["chunks"] = len(chunk_rows)
    stats["chunks_embedded"] = embedded
    con.execute("INSERT INTO meta VALUES ('stats', ?)", (json.dumps(stats, ensure_ascii=False),))
    con.commit()
    con.close()
    stats_path = root / cfg["index"]["stats_path"]
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    z = stats["zettel"]
    print(f"notes: {sum(stats['notes_by_layer'].values())} {stats['notes_by_layer']}")
    print(f"links: {stats['total_links']}（未解決 {stats['unresolved_links']}） / chunks: {stats['chunks']}（埋め込み済 {embedded}）")
    print(f"zettel: {z['count']} / 被リンク0: {len(z['orphans_no_inlink'])} / 発リンク0: {len(z['no_outlink'])} / 文献への発リンク: {z['links_to_literature']}")
    print(f"→ {db_path.relative_to(root)} / {stats_path.relative_to(root)}")
