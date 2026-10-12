#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arxiv — 学术论文检索 CLI（供 AI agent / 脚本调用）

数据源：arXiv 官方 API（export.arxiv.org，免费、无需密钥），返回 Atom。
支持关键词/标题/作者/分类检索、按提交日期或相关度排序、按 ID 取论文。

默认 JSON 输出；全局 --table/--compact/--fields。错误带 code，退出码 1。
仅使用 Python 标准库。
"""
import argparse
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
NS = {"a": "http://www.w3.org/2005/Atom",
      "arxiv": "http://arxiv.org/schemas/atom",
      "os": "http://a9.com/-/spec/opensearch/1.1/"}

CATEGORIES = {
    "cs.AI": "人工智能", "cs.CL": "计算语言学/NLP", "cs.CV": "计算机视觉",
    "cs.LG": "机器学习", "cs.RO": "机器人", "cs.SE": "软件工程",
    "cs.CR": "密码与安全", "cs.DB": "数据库", "cs.IR": "信息检索",
    "stat.ML": "统计机器学习", "math.OC": "优化与控制",
    "eess.IV": "图像与视频处理", "q-bio.BM": "生物分子",
}


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def http_text(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 502, 503, 504):
                raise
        except urllib.error.URLError as e:
            last = e
        if attempt < 2:
            time.sleep(1.0 * (attempt + 1))  # arXiv 限流友好
    raise last


def parse_feed(text):
    root = ET.fromstring(text)
    total = root.findtext("os:totalResults", default=None, namespaces=NS)
    papers = []
    for e in root.findall("a:entry", NS):
        def txt(path):
            el = e.find(path, NS)
            return (el.text or "").strip() if el is not None else ""
        aid = txt("a:id").rsplit("/", 1)[-1]
        authors = [a.findtext("a:name", default="", namespaces=NS)
                   for a in e.findall("a:author", NS)]
        cats = [c.get("term") for c in e.findall("a:category", NS)]
        pdf = ""
        for ln in e.findall("a:link", NS):
            if ln.get("title") == "pdf":
                pdf = ln.get("href")
        papers.append({
            "id": aid,
            "id_base": re.sub(r"v\d+$", "", aid),
            "title": re.sub(r"\s+", " ", txt("a:title")),
            "summary": re.sub(r"\s+", " ", txt("a:summary")),
            "authors": authors,
            "published": txt("a:published")[:10],
            "updated": txt("a:updated")[:10],
            "categories": cats,
            "primary_category": (e.find("arxiv:primary_category", NS)
                                 .get("term") if e.find(
                                     "arxiv:primary_category", NS)
                                 is not None else (cats[0] if cats else None)),
            "abs_url": f"https://arxiv.org/abs/{re.sub(r'v[0-9]+$', '', aid)}",
            "pdf_url": pdf,
            "doi": txt("arxiv:doi") or None,
            "comment": txt("arxiv:comment") or None,
        })
    return (int(total) if total else len(papers)), papers


def query_api(params):
    q = urllib.parse.urlencode(params)
    return parse_feed(http_text(f"https://export.arxiv.org/api/query?{q}"))


def cmd_search(args):
    terms = []
    if args.query:
        terms.append(f"all:{args.query}")
    if args.title:
        terms.append(f'ti:"{args.title}"')
    if args.author:
        terms.append(f'au:"{args.author}"')
    if args.category:
        terms.append(f"cat:{args.category}")
    if not terms:
        fail("至少给一个检索条件（关键词/--title/--author/--category）",
             code="INVALID")
    total, papers = query_api({
        "search_query": " AND ".join(terms),
        "start": args.start, "max_results": args.limit,
        "sortBy": "submittedDate" if args.sort == "date" else "relevance",
        "sortOrder": "descending"})
    emit({"query": " AND ".join(terms), "total": total, "results": papers},
         args, cols=["id", "published", "title"])


def cmd_recent(args):
    total, papers = query_api({
        "search_query": f"cat:{args.category}",
        "start": 0, "max_results": args.limit,
        "sortBy": "submittedDate", "sortOrder": "descending"})
    emit({"category": args.category,
          "category_name": CATEGORIES.get(args.category),
          "total": total, "results": papers}, args,
         cols=["id", "published", "title"])


def cmd_paper(args):
    aid = args.id.replace("arxiv:", "").strip()
    total, papers = query_api({"id_list": aid})
    if not papers:
        fail(f"论文不存在: {aid}", code="NOT_FOUND")
    emit(papers[0], args)


def cmd_categories(args):
    rows = [{"code": k, "name": v} for k, v in CATEGORIES.items()]
    emit({"note": "常用分类速查（完整分类见 arxiv.org/category_taxonomy）",
          "results": rows}, args, cols=["code", "name"])


def cmd_doctor(args):
    checks = []
    t0 = time.time()
    try:
        total, papers = query_api({"search_query": "all:transformer",
                                   "max_results": 1})
        checks.append({"name": "arxiv_api", "ok": len(papers) == 1,
                       "ms": int((time.time() - t0) * 1000)})
    except Exception as e:
        checks.append({"name": "arxiv_api", "ok": False,
                       "ms": int((time.time() - t0) * 1000),
                       "detail": str(e)[:160]})
    ok = all(c["ok"] for c in checks)
    emit({"ok": ok, "checks": checks}, args)
    if not ok:
        sys.exit(1)


COMMANDS_MANIFEST = [
    {"name": "search", "usage": "arxiv search <关键词> [--author 名] "
     "[--title 词] [--category cs.CL] [--sort date|relevance] [--limit N]",
     "desc": "论文检索（arXiv 官方 API）"},
    {"name": "recent", "usage": "arxiv recent <分类代码> [--limit N]",
     "desc": "某分类最新提交（如 cs.CL/cs.AI/cs.LG）"},
    {"name": "paper", "usage": "arxiv paper <arXiv ID>",
     "desc": "按 ID 取单篇（标题/摘要/作者/分类/PDF 链接）"},
    {"name": "categories", "usage": "arxiv categories", "desc": "常用分类速查"},
    {"name": "doctor", "usage": "arxiv doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "arxiv commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "摘要为英文原文；错误带 code"}, args)


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
            v = r.get(cols[0]) if cols else ""
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
    p = argparse.ArgumentParser(prog="arxiv", description="arXiv 论文检索 CLI（官方 API，免密钥）")
    p.add_argument("--version", action="version", version=f"arxiv {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="论文检索")
    sp.add_argument("query", nargs="?", default="")
    sp.add_argument("--title", default="")
    sp.add_argument("--author", default="")
    sp.add_argument("--category", default="")
    sp.add_argument("--sort", default="relevance", choices=["relevance", "date"])
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--start", type=int, default=0)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("recent", help="某分类最新论文")
    sp.add_argument("category")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_recent)

    sp = sub.add_parser("paper", help="按 ID 取论文")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_paper)

    sp = sub.add_parser("categories", help="常用分类速查")
    sp.set_defaults(func=cmd_categories)

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
