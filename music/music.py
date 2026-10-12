#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
music — 音乐元数据检索 CLI（供 AI agent / 脚本调用）

数据源（均官方 / 开放、免密钥）：
  * iTunes Search API  itunes.apple.com —— 歌曲/专辑/歌手 + 30 秒试听 + 封面
  * MusicBrainz        musicbrainz.org —— 开放音乐百科（录音/发行/艺人）

定位：音乐元数据检索，不是播放器——不提供完整歌曲播放地址、不下载音乐。
默认 JSON 输出；--table 表格；--compact 单行；--fields 裁剪。
错误时 stderr 输出 {"error": ..., "code": ...} 且退出码 1。
仅使用 Python 标准库。
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
MB_UA = "agent-music-cli/1.0 (contact: local)"
TIMEOUT = 25
VERSION = "1.0.0"

ITUNES = "https://itunes.apple.com"
MB = "https://musicbrainz.org/ws/2"

_mb_last = [0.0]  # MusicBrainz 官方限速 1 req/s，本地节流


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def http_json(url, ua=UA):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8", errors="ignore"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (502, 503, 504):
                raise
        except urllib.error.URLError as e:
            last = e
        if attempt < 2:
            time.sleep(0.7 * (attempt + 1))
    raise last


def mb_json(path):
    """MusicBrainz 请求：专用 UA + ≥1.1 秒节流（官方限速 1 次/秒）。"""
    wait = 1.1 - (time.time() - _mb_last[0])
    if wait > 0:
        time.sleep(wait)
    try:
        return http_json(MB + path, ua=MB_UA)
    finally:
        _mb_last[0] = time.time()


# ---------------------------------------------------------------- iTunes

def _artwork600(url):
    if url and "100x100" in url:
        return url.replace("100x100", "600x600")
    return url


def _fmt_dur(ms):
    if not ms:
        return None
    s = int(round(ms / 1000))
    return f"{s // 60}:{s % 60:02d}"


def shape_itunes(r):
    """按 wrapperType/kind 归一 iTunes 结果（字段以真实响应为准）。"""
    wt = r.get("wrapperType")
    kind = r.get("kind")
    base = {
        "type": ("song" if kind == "song" else
                 "album" if wt == "collection" else
                 "artist" if wt == "artist" else wt),
        "artist_name": r.get("artistName"),
        "artist_id": r.get("artistId"),
        "genre": r.get("primaryGenreName"),
    }
    if base["type"] == "artist":
        base.update({"artist_name": r.get("artistName"),
                     "url": r.get("artistLinkUrl")})
        return {k: v for k, v in base.items() if v is not None}
    if base["type"] == "album":
        base.update({
            "collection_id": r.get("collectionId"),
            "collection_name": r.get("collectionName"),
            "track_count": r.get("trackCount"),
            "release_date": r.get("releaseDate"),
            "price": r.get("collectionPrice"),
            "currency": r.get("currency"),
            "artwork": _artwork600(r.get("artworkUrl100")),
            "url": r.get("collectionViewUrl"),
        })
        return {k: v for k, v in base.items() if v is not None}
    base.update({
        "track_id": r.get("trackId"),
        "track_name": r.get("trackName"),
        "collection_id": r.get("collectionId"),
        "collection_name": r.get("collectionName"),
        "release_date": r.get("releaseDate"),
        "duration_ms": r.get("trackTimeMillis"),
        "duration": _fmt_dur(r.get("trackTimeMillis")),
        "price": r.get("trackPrice"),
        "currency": r.get("currency"),
        "preview_url": r.get("previewUrl"),
        "artwork": _artwork600(r.get("artworkUrl100")),
        "url": r.get("trackViewUrl"),
    })
    return {k: v for k, v in base.items() if v is not None}


ENTITY_MAP = {"song": "song", "album": "album", "artist": "musicArtist"}
LOOKUP_ENTITY = {"song": "song", "album": "song", "artist": "album"}


def itunes_search(term, entity, limit, country):
    # iTunes 小 limit 有怪癖：limit=1 实测恒返回 0 条；limit<5 时按 5 取再截断
    fetch = max(limit, 5) if limit < 5 else limit
    q = urllib.parse.urlencode({
        "media": "music", "entity": ENTITY_MAP[entity], "term": term,
        "limit": fetch, "country": country})
    data = http_json(f"{ITUNES}/search?{q}")
    return (data.get("results") or [])[:limit]


def cmd_search(args):
    rows = itunes_search(args.term, args.entity, args.limit, args.country)
    out = {"source": "itunes", "query": args.term, "entity": args.entity,
           "storefront": args.country, "count": len(rows),
           "results": [shape_itunes(r) for r in rows],
           "note": f"结果来自 Apple {args.country} 区商店曲库"
                   + ("；preview_url 为 30 秒试听" if args.entity == "song"
                      else "")}
    if not rows and args.country == "CN":
        out["note"] = ("大陆区（CN）iTunes 商店音乐搜索实测恒返回 0 条，"
                       "请改用 --country US 或 HK")
    cols = {"song": ["track_name", "artist_name", "collection_name",
                     "duration", "release_date", "genre"],
            "album": ["collection_name", "artist_name", "track_count",
                      "release_date", "genre"],
            "artist": ["artist_name", "genre"]}[args.entity]
    emit(out, args, cols=cols)


def cmd_lookup(args):
    q = urllib.parse.urlencode({"id": args.id, "entity": LOOKUP_ENTITY[args.entity],
                                "country": args.country})
    data = http_json(f"{ITUNES}/lookup?{q}")
    rows = data.get("results") or []
    # lookup 返回 wrapper 在前：查专辑是 [专辑, 曲目...]，查歌手是其专辑列表
    items = [shape_itunes(r) for r in rows]
    if not items:
        fail(f"iTunes 查不到 id={args.id}", code="NOT_FOUND")
    emit({"source": "itunes", "id": args.id, "entity": args.entity,
          "storefront": args.country, "results": items}, args,
         cols=["track_name", "collection_name", "artist_name", "duration"])


# ---------------------------------------------------------------- MusicBrainz

def _artists_of(item):
    names = []
    for c in item.get("artist-credit") or []:
        if isinstance(c, dict):
            a = c.get("artist") or {}
            names.append(c.get("name") or a.get("name"))
    return " & ".join(n for n in names if n) or None


def shape_mb(kind, r):
    if kind == "artist":
        life = r.get("life-span") or {}
        return {"type": "artist", "id": r.get("id"), "name": r.get("name"),
                "sort_name": r.get("sort-name"),
                "artist_type": r.get("type"), "country": r.get("country"),
                "area": (r.get("area") or {}).get("name"),
                "begin": life.get("begin"), "end": life.get("end"),
                "disambiguation": r.get("disambiguation"),
                "score": r.get("score")}
    if kind == "release":
        return {"type": "release", "id": r.get("id"), "title": r.get("title"),
                "artist": _artists_of(r), "date": r.get("date"),
                "country": r.get("country"), "status": r.get("status"),
                "barcode": r.get("barcode"), "score": r.get("score")}
    rel = (r.get("releases") or [{}])[0]
    return {"type": "recording", "id": r.get("id"), "title": r.get("title"),
            "artist": _artists_of(r), "duration": _fmt_dur(r.get("length")),
            "duration_ms": r.get("length"),
            "first_release_date": r.get("first-release-date"),
            "isrcs": r.get("isrcs"), "score": r.get("score"),
            "release": rel.get("title"),
            "release_date": rel.get("date")}


def cmd_mb(args):
    q = urllib.parse.urlencode({"query": args.term, "fmt": "json",
                                "limit": args.limit})
    data = mb_json(f"/{args.kind}/?{q}")
    key = {"recording": "recordings", "release": "releases",
           "artist": "artists"}[args.kind]
    rows = data.get(key) or []
    out = {"source": "musicbrainz", "query": args.term, "kind": args.kind,
           "total": data.get("count"), "count": len(rows),
           "results": [{k: v for k, v in shape_mb(args.kind, r).items()
                        if v is not None} for r in rows],
           "note": "score 为 MusicBrainz 相关性分（0-100）；中文 query 相关性一般，请结合 score 判断"}
    cols = {"recording": ["title", "artist", "duration",
                          "first_release_date", "score"],
            "release": ["title", "artist", "date", "country", "score"],
            "artist": ["name", "country", "artist_type", "score"]}[args.kind]
    emit(out, args, cols=cols)


def cmd_doctor(args):
    checks = []

    def probe_itunes():
        rows = itunes_search("Jay Chou", "song", 1, "US")
        if not rows:
            raise RuntimeError("iTunes US 搜索返回 0 条")
        return rows[0].get("trackName")

    def probe_mb():
        q = urllib.parse.urlencode({"query": "Jay Chou", "fmt": "json",
                                    "limit": 1})
        data = mb_json(f"/artist/?{q}")
        if not (data.get("artists")):
            raise RuntimeError("MusicBrainz 搜索返回 0 条")
        return data["artists"][0].get("name")

    for name, fn in (("itunes_search_us", probe_itunes),
                     ("musicbrainz", probe_mb)):
        t0 = time.time()
        try:
            detail = fn()
            checks.append({"name": name, "ok": True,
                           "ms": int((time.time() - t0) * 1000),
                           "detail": str(detail)[:80]})
        except Exception as e:
            checks.append({"name": name, "ok": False,
                           "ms": int((time.time() - t0) * 1000),
                           "detail": str(e)[:160]})
    ok = all(c["ok"] for c in checks)
    emit({"ok": ok, "checks": checks}, args)
    if not ok:
        sys.exit(1)


COMMANDS_MANIFEST = [
    {"name": "search", "usage": "music search <关键词> [--entity song|album|artist] [--limit N] [--country US]",
     "desc": "iTunes 搜歌曲/专辑/歌手：试听链接、封面、价格、发行日期（默认美区；CN 区音乐搜索实测恒空）"},
    {"name": "lookup", "usage": "music lookup <id> [--entity song|album|artist] [--country US]",
     "desc": "按 iTunes 的 track/collection/artist id 查详情（album 返回曲目列表）"},
    {"name": "mb", "usage": "music mb <关键词> [--kind recording|release|artist] [--limit N]",
     "desc": "MusicBrainz 开放音乐百科检索：录音（含 ISRC）/发行版本/艺人，带相关性 score"},
    {"name": "doctor", "usage": "music doctor", "desc": "通道健康检查（iTunes US + MusicBrainz）"},
    {"name": "commands", "usage": "music commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "定位为音乐元数据检索，无完整歌曲播放/下载；错误带 code"}, args)


# ---------------------------------------------------------------- output

_LIST_KEYS = ("results", "checks")


def _pick_fields(obj, fields):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in _LIST_KEYS and isinstance(v, list):
                out[k] = [{kk: vv for kk, vv in row.items() if kk in fields}
                          if isinstance(row, dict) else row for row in v]
            elif k in fields:
                out[k] = v
        return out
    if isinstance(obj, list):
        return [{k: v for k, v in row.items() if k in fields}
                if isinstance(row, dict) else row for row in obj]
    return obj


def emit(data, args, cols=None):
    if getattr(args, "table", False):
        rows = data
        if isinstance(data, dict):
            for k in _LIST_KEYS:
                if k in data:
                    meta = {kk: vv for kk, vv in data.items() if kk != k}
                    if meta:
                        print(f"# {meta}")
                    rows = data[k]
                    break
            else:
                rows = [data]
        if isinstance(rows, dict):
            rows = [rows]
        cols = cols or (list(rows[0].keys()) if rows else [])
        print("\t".join(str(c) for c in cols))
        for r in rows:
            print("\t".join("" if r.get(c) is None else str(r.get(c))
                            for c in cols))
    else:
        fields = getattr(args, "fields", None)
        if fields:
            data = _pick_fields(data, set(fields))
        if getattr(args, "compact", False):
            print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(prog="music", description="音乐元数据 CLI（iTunes + MusicBrainz，免密钥）")
    p.add_argument("--version", action="version", version=f"music {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="iTunes 搜索（歌曲/专辑/歌手）")
    sp.add_argument("term")
    sp.add_argument("--entity", choices=["song", "album", "artist"],
                    default="song")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--country", default="US")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("lookup", help="按 iTunes id 查详情")
    sp.add_argument("id")
    sp.add_argument("--entity", choices=["song", "album", "artist"],
                    default="song")
    sp.add_argument("--country", default="US")
    sp.set_defaults(func=cmd_lookup)

    sp = sub.add_parser("mb", help="MusicBrainz 检索")
    sp.add_argument("term")
    sp.add_argument("--kind", choices=["recording", "release", "artist"],
                    default="recording")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_mb)

    sp = sub.add_parser("doctor", help="通道健康检查")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("commands", help="能力清单")
    sp.set_defaults(func=cmd_commands)

    argv = sys.argv[1:]
    table_flag = "--table" in argv
    compact_flag = "--compact" in argv
    fields, cleaned, i = None, [], 0
    while i < len(argv):
        a = argv[i]
        if a in ("--table", "--compact"):
            i += 1
        elif a == "--fields" and i + 1 < len(argv):
            fields = [x.strip() for x in argv[i + 1].split(",") if x.strip()]
            i += 2
        elif a.startswith("--fields="):
            fields = [x.strip() for x in a[9:].split(",") if x.strip()]
            i += 1
        else:
            cleaned.append(a)
            i += 1
    args = p.parse_args(cleaned)
    args.table, args.compact, args.fields = table_flag, compact_flag, fields
    try:
        args.func(args)
    except BrokenPipeError:
        pass
    except Exception as e:
        code = "INTERNAL"
        if isinstance(e, urllib.error.HTTPError):
            code = {404: "NOT_FOUND", 429: "RATE_LIMIT"}.get(
                e.code, "UPSTREAM" if e.code >= 500 else "HTTP")
        elif isinstance(e, urllib.error.URLError):
            code = "NETWORK"
        elif isinstance(e, RuntimeError):
            code = "UPSTREAM"
        fail(str(e), code=code)


if __name__ == "__main__":
    main()
