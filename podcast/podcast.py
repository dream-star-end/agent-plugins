#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
podcast — 播客搜索与单集列表 CLI（供 AI agent / 脚本调用）

数据源（均免密钥）：
  * 搜索/节目  iTunes Search API（itunes.apple.com/search|lookup）
  * 单集列表   节目自身的 RSS feed（xml.etree 解析 channel/item）

默认 JSON 输出；--table 表格；--compact 单行；--fields 裁剪。
错误时 stderr 输出 {"error": ..., "code": ...} 且退出码 1。
仅使用 Python 标准库。
"""
import argparse
import email.utils
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
TIMEOUT = 30
VERSION = "1.0.0"
ITUNES_NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def _open(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


_RETRYABLE = (urllib.error.URLError, ConnectionError,
              http.client.HTTPException)


def http_json(url):
    last = None
    for attempt in range(3):
        try:
            with _open(url) as resp:
                return json.loads(resp.read().decode("utf-8", errors="ignore"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (502, 503, 504):
                raise
        except _RETRYABLE as e:
            last = e
        if attempt < 2:
            time.sleep(0.7 * (attempt + 1))
    raise last


def http_bytes(url):
    last = None
    for attempt in range(3):
        try:
            with _open(url) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (502, 503, 504):
                raise
        except _RETRYABLE as e:
            last = e
        if attempt < 2:
            time.sleep(0.7 * (attempt + 1))
    raise last


def strip_html(text):
    t = re.sub(r"<[^>]+>", " ", text or "")
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(t)).strip()


def itunes_search(term, limit, country):
    q = urllib.parse.urlencode({"media": "podcast", "term": term,
                                "limit": limit, "country": country})
    return http_json(f"https://itunes.apple.com/search?{q}")


def itunes_lookup(collection_id):
    q = urllib.parse.urlencode({"id": collection_id})
    data = http_json(f"https://itunes.apple.com/lookup?{q}")
    rows = data.get("results") or []
    if not rows:
        fail(f"iTunes 里找不到节目 id: {collection_id}", code="NOT_FOUND")
    return rows[0]


def shape_show(r):
    return {"id": r.get("collectionId"), "title": r.get("collectionName"),
            "author": r.get("artistName"), "episodes": r.get("trackCount"),
            "genre": r.get("primaryGenreName"), "feed": r.get("feedUrl"),
            "country": r.get("country"),
            "latest_release": (r.get("releaseDate") or "")[:10] or None,
            "artwork": r.get("artworkUrl600") or r.get("artworkUrl100")}


def _duration_sec(raw):
    """itunes:duration 可能是 'SS'、'MM:SS' 或 'HH:MM:SS'，统一换算秒。"""
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    try:
        sec = 0
        for part in raw.split(":"):
            sec = sec * 60 + int(float(part))
        return sec
    except ValueError:
        return None


def _pub_iso(raw):
    if not raw:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        return dt.isoformat()
    except (TypeError, ValueError):
        return raw


def parse_feed(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        fail(f"RSS 解析失败: {e}", code="UPSTREAM")
    channel = root.find("channel")
    if channel is None:
        fail("不是 RSS 2.0 feed（无 channel 节点；Atom feed 暂不支持）",
             code="UPSTREAM")
    show = {"title": channel.findtext("title"),
            "link": channel.findtext("link"),
            "description": strip_html(channel.findtext("description"))[:200]
                           or None,
            "language": channel.findtext("language")}
    episodes = []
    for item in channel.findall("item"):
        enc = item.find("enclosure")
        dur_raw = item.findtext("itunes:duration", namespaces=ITUNES_NS)
        desc = item.findtext("description")
        if not desc:
            desc = item.findtext("itunes:summary", namespaces=ITUNES_NS)
        episodes.append({
            "title": item.findtext("title"),
            "published": _pub_iso(item.findtext("pubDate")),
            "duration": dur_raw.strip() if dur_raw else None,
            "duration_sec": _duration_sec(dur_raw),
            "audio": enc.get("url") if enc is not None else None,
            "audio_type": enc.get("type") if enc is not None else None,
            "size_bytes": int(enc.get("length"))
                          if enc is not None and (enc.get("length") or "")
                          .isdigit() else None,
            "summary": strip_html(desc)[:200] or None,
            "guid": item.findtext("guid"),
        })
    return show, episodes


def cmd_search(args):
    # 实测 iTunes 对小 limit 返回偏少（limit=1 恒为 0、limit=3 只回 2），
    # limit<5 时按 5 取再截断，避免误报"搜不到"
    fetch_n = max(args.limit, 5) if args.limit < 5 else args.limit
    data = itunes_search(args.keyword, fetch_n, args.country)
    items = [shape_show(r)
             for r in (data.get("results") or [])[:args.limit]]
    out = {"query": args.keyword, "country": args.country,
           "count": len(items), "results": items}
    if not items and args.country != "US":
        out["note"] = (f"在 {args.country} 区 iTunes 索引里没搜到；"
                       "可加 --country US 再试")
    emit(out, args, cols=["id", "title", "author", "episodes", "genre"])


def cmd_episodes(args):
    ref = str(args.ref).strip()
    if ref.startswith(("http://", "https://")):
        feed_url, show_hint = ref, {}
    elif ref.isdigit():
        row = itunes_lookup(ref)
        feed_url = row.get("feedUrl")
        if not feed_url:
            fail(f"节目 {ref} 在 iTunes 里没有 feedUrl", code="NOT_FOUND")
        show_hint = shape_show(row)
    else:
        fail("episodes 参数需为 iTunes collectionId（数字）或 RSS feed URL",
             code="INVALID")
    try:
        raw = http_bytes(feed_url)
    except urllib.error.HTTPError as e:
        fail(f"RSS 抓取失败 HTTP {e.code}: {feed_url}", code="UPSTREAM")
    except urllib.error.URLError as e:
        fail(f"RSS 抓取失败: {e}（{feed_url}）", code="NETWORK")
    show, episodes = parse_feed(raw)
    show = {**show_hint, **{k: v for k, v in show.items() if v}}
    show["feed"] = feed_url
    emit({"podcast": show, "total_in_feed": len(episodes),
          "results": episodes[:args.limit]}, args,
         cols=["published", "title", "duration", "audio"])


def cmd_doctor(args):
    checks = []

    def check_itunes():
        d = itunes_search("科技", 5, "CN")
        if not (d.get("results")):
            raise RuntimeError("search 返回空")

    def check_lookup():
        row = itunes_lookup(1494812579)  # 声动活泼《What's Next｜科技早知道》
        if not row.get("feedUrl"):
            raise RuntimeError("lookup 无 feedUrl")

    def check_rss():
        with _open("https://feeds.fireside.fm/guiguzaozhidao/rss") as resp:
            head = resp.read(4096)
        if b"<rss" not in head and b"<channel" not in head:
            raise RuntimeError("RSS 头部异常")

    for name, fn in (("itunes_search", check_itunes),
                     ("itunes_lookup", check_lookup),
                     ("rss_fetch", check_rss)):
        t0 = time.time()
        try:
            fn()
            checks.append({"name": name, "ok": True,
                           "ms": int((time.time() - t0) * 1000)})
        except Exception as e:
            checks.append({"name": name, "ok": False,
                           "ms": int((time.time() - t0) * 1000),
                           "detail": str(e)[:160]})
    ok = all(c["ok"] for c in checks)
    emit({"ok": ok, "checks": checks}, args)
    if not ok:
        sys.exit(1)


COMMANDS_MANIFEST = [
    {"name": "search", "usage": "podcast search <关键词> [--limit N] "
     "[--country CN|US]", "desc": "按关键词搜播客（iTunes 索引，含 feed 地址）"},
    {"name": "episodes", "usage": "podcast episodes <collectionId|feedUrl> "
     "[--limit N]", "desc": "解析节目 RSS，列单集（标题/发布时间/时长/音频直链/摘要）"},
    {"name": "doctor", "usage": "podcast doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "podcast commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "搜索范围是 iTunes 索引（按 --country 分区）；"
                         "单集来自节目 RSS，错误带 code"}, args)


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
    p = argparse.ArgumentParser(prog="podcast", description="播客 CLI（iTunes Search API + RSS，免密钥）")
    p.add_argument("--version", action="version", version=f"podcast {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="搜索播客")
    sp.add_argument("keyword")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--country", default="CN")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("episodes", help="单集列表（collectionId 或 feed URL）")
    sp.add_argument("ref")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_episodes)

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
        elif isinstance(e, (urllib.error.URLError, ConnectionError,
                            http.client.HTTPException)):
            code = "NETWORK"
        elif isinstance(e, RuntimeError):
            code = "UPSTREAM"
        fail(str(e), code=code)


if __name__ == "__main__":
    main()
