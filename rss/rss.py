#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rss — RSS/Atom 订阅阅读 CLI（供 AI agent / 脚本调用）

能力：抓取并解析 RSS 2.0 / RSS 1.0(RDF) / Atom feed，统一字段输出；
内置一份经实测可达的常用源速查表（feeds）。
默认 JSON 输出；--table 表格；--compact 单行；--fields 裁剪。
错误时 stderr 输出 {"error": ..., "code": ...} 且退出码 1。
仅使用 Python 标准库。
"""
import argparse
import email.utils
import gzip
import html as _html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "Chrome/126 Safari/537.36")
TIMEOUT = 25
VERSION = "1.0.0"
ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"
RDF_ROOT = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"
RSS1 = "{http://purl.org/rss/1.0/}"

# 内置源：仅收录 2026-10-12 实测可达且可被标准 XML 解析的源。
# 机器之心 https://www.jiqizhixin.com/rss 返回的 XML 标签不闭合、标准
# 解析器报错，未收录（见 README 边界）。
BUILTIN_FEEDS = [
    {"name": "阮一峰的网络日志", "url": "http://www.ruanyifeng.com/blog/atom.xml",
     "note": "科技/互联网随笔，Atom"},
    {"name": "V2EX 最新主题", "url": "https://www.v2ex.com/index.xml",
     "note": "程序员社区热帖，Atom"},
    {"name": "少数派", "url": "https://sspai.com/feed",
     "note": "数码与效率媒体，RSS 2.0"},
    {"name": "量子位", "url": "https://www.qbitai.com/feed",
     "note": "AI 科技媒体，RSS 2.0"},
    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss",
     "note": "技术社区头条，RSS 2.0"},
    {"name": "BBC 中文", "url": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml",
     "note": "国际新闻中文版，RSS 2.0"},
    {"name": "GitHub 官方博客", "url": "https://github.blog/feed/",
     "note": "GitHub 产品与工程，RSS 2.0"},
    {"name": "Python 官方博客", "url": "https://blog.python.org/feeds/posts/default",
     "note": "Python 语言动态，RSS 2.0"},
    {"name": "NASA 新闻", "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
     "note": "航天新闻，RSS 2.0"},
]


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def http_bytes(url):
    h = {"User-Agent": UA,
         "Accept": "application/rss+xml, application/atom+xml, "
                   "application/xml, text/xml, */*"}
    req = urllib.request.Request(url, headers=h)
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                b = resp.read()
            if b[:2] == b"\x1f\x8b":
                b = gzip.decompress(b)
            return b
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (502, 503, 504):
                raise
        except Exception as e:
            last = e
        if attempt < 2:
            time.sleep(0.7 * (attempt + 1))
    raise last


def strip_html(s, limit=200):
    text = re.sub(r"<[^>]+>", " ", s or "")
    text = re.sub(r"\s+", " ", _html.unescape(text)).strip()
    return text[:limit] if text else None


def norm_date(s):
    """RFC822 / ISO8601 -> 'YYYY-MM-DD HH:MM'；失败保留原文。"""
    if not s:
        return None
    s = s.strip()
    try:
        dt = email.utils.parsedate_to_datetime(s)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    iso = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s


def _text(el, path):
    c = el.find(path)
    if c is None:
        return None
    t = (c.text or "").strip()
    return t or None


def parse_feed(raw, feed_url):
    """解析 RSS2.0 / RSS1.0(RDF) / Atom，返回统一结构 dict。"""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        fail(f"XML 解析失败（源返回的不是合法 feed）: {e}", code="UPSTREAM")
    if root.tag == "rss":
        channel = root.find("channel")
        if channel is None:
            fail("RSS 缺少 channel 节点", code="UPSTREAM")
        items = []
        for it in channel.findall("item"):
            author = (_text(it, f"{DC}creator") or _text(it, "author"))
            summary = (strip_html(_text(it, "description"))
                       or strip_html(_text(it, f"{CONTENT}encoded")))
            items.append({
                "title": _text(it, "title"),
                "link": _text(it, "link"),
                "published": norm_date(_text(it, "pubDate")
                                       or _text(it, f"{DC}date")),
                "author": author,
                "summary": summary})
        return {"format": "rss2.0",
                "feed_title": _text(channel, "title"),
                "feed_link": _text(channel, "link"),
                "feed_url": feed_url, "items": items}
    if root.tag == RDF_ROOT:
        channel = root.find(f"{RSS1}channel")
        items = []
        for it in root.findall(f"{RSS1}item"):
            items.append({
                "title": _text(it, f"{RSS1}title"),
                "link": _text(it, f"{RSS1}link"),
                "published": norm_date(_text(it, f"{DC}date")),
                "author": _text(it, f"{DC}creator"),
                "summary": strip_html(_text(it, f"{RSS1}description"))})
        return {"format": "rss1.0",
                "feed_title": _text(channel, f"{RSS1}title")
                if channel is not None else None,
                "feed_link": _text(channel, f"{RSS1}link")
                if channel is not None else None,
                "feed_url": feed_url, "items": items}
    if root.tag == f"{ATOM}feed":
        def atom_link(el):
            links = el.findall(f"{ATOM}link")
            for ln in links:
                if ln.get("rel") in (None, "alternate"):
                    return ln.get("href")
            return links[0].get("href") if links else None
        items = []
        for e in root.findall(f"{ATOM}entry"):
            author = None
            a = e.find(f"{ATOM}author")
            if a is not None:
                author = _text(a, f"{ATOM}name")
            summary = (strip_html(_text(e, f"{ATOM}summary"))
                       or strip_html(_text(e, f"{ATOM}content")))
            items.append({
                "title": _text(e, f"{ATOM}title"),
                "link": atom_link(e),
                "published": norm_date(_text(e, f"{ATOM}published")
                                       or _text(e, f"{ATOM}updated")),
                "author": author,
                "summary": summary})
        return {"format": "atom",
                "feed_title": _text(root, f"{ATOM}title"),
                "feed_link": atom_link(root),
                "feed_url": feed_url, "items": items}
    fail(f"无法识别的 feed 根节点: {root.tag}", code="UPSTREAM")


def cmd_read(args):
    raw = http_bytes(args.url)
    feed = parse_feed(raw, args.url)
    total = len(feed["items"])
    feed["total"] = total
    feed["results"] = feed.pop("items")[:args.limit]
    emit(feed, args, cols=["published", "title", "author"])


def cmd_feeds(args):
    emit({"total": len(BUILTIN_FEEDS), "results": BUILTIN_FEEDS}, args,
         cols=["name", "url", "note"])


def cmd_doctor(args):
    checks = []
    for f in BUILTIN_FEEDS:
        t0 = time.time()
        try:
            http_bytes(f["url"])
            checks.append({"name": f["name"], "ok": True,
                           "ms": int((time.time() - t0) * 1000)})
        except Exception as e:
            checks.append({"name": f["name"], "ok": False,
                           "ms": int((time.time() - t0) * 1000),
                           "detail": str(e)[:120]})
    t0 = time.time()
    try:
        feed = parse_feed(http_bytes(BUILTIN_FEEDS[0]["url"]),
                          BUILTIN_FEEDS[0]["url"])
        ok_parse = len(feed["items"]) > 0
        checks.append({"name": "parse_sample", "ok": ok_parse,
                       "ms": int((time.time() - t0) * 1000),
                       "detail": f"{feed['format']} / {feed['feed_title']} / "
                                 f"{len(feed['items'])} 条"})
    except Exception as e:
        checks.append({"name": "parse_sample", "ok": False,
                       "ms": int((time.time() - t0) * 1000),
                       "detail": str(e)[:120]})
    parse_check = checks[-1]
    emit({"ok": parse_check["ok"],
          "note": "ok 以示例源解析为准；个别内置源可达性见 checks（源站"
                  "偶发慢/限流时单项 ok=false 不代表解析不可用）",
          "checks": checks}, args)
    if not parse_check["ok"]:
        sys.exit(1)


COMMANDS_MANIFEST = [
    {"name": "read", "usage": "rss read <feed URL> [--limit N]",
     "desc": "抓取并解析 RSS 2.0 / RSS 1.0 / Atom feed，统一字段输出"},
    {"name": "feeds", "usage": "rss feeds",
     "desc": "内置常用源速查表（均经实测可达且可解析）"},
    {"name": "doctor", "usage": "rss doctor",
     "desc": "逐个检查内置源可达性 + 示例源解析"},
    {"name": "commands", "usage": "rss commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "summary 已去 HTML 并截断；日期尽量归一化为 "
                         "YYYY-MM-DD HH:MM；错误带 code"}, args)


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
    p = argparse.ArgumentParser(prog="rss", description="RSS/Atom 订阅阅读 CLI（标准库解析，免密钥）")
    p.add_argument("--version", action="version", version=f"rss {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("read", help="抓取并解析一个 feed")
    sp.add_argument("url")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("feeds", help="内置常用源速查表")
    sp.set_defaults(func=cmd_feeds)

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
