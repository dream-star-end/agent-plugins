#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
openalex — 学术全库检索 CLI（供 AI agent / 脚本调用）

数据源：OpenAlex API（开放学术图谱，免费、无需密钥）
  * 论文  api.openalex.org/works
  * 作者  api.openalex.org/authors
请求带 mailto 参数走 polite pool（响应更快、限额更宽）。

摘要说明：OpenAlex 出于版权原因不直接给摘要全文，只给
abstract_inverted_index（{词: [出现位置]} 倒排索引），本工具按位置
还原成可读摘要文本；部分论文无此索引，abstract 返回 null。

引用计数为 OpenAlex 自有学术图谱口径，与 Google Scholar /
Web of Science 不一致，跨源不可直接比较。

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

UA = "openalex-cli/1.0 (mailto:agent@example.com)"
MAILTO = "agent@example.com"
TIMEOUT = 30
VERSION = "1.0.0"
API = "https://api.openalex.org"


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def http_json(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
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


def api_get(path, params=None):
    q = {"mailto": MAILTO}
    q.update(params or {})
    return http_json(f"{API}{path}?{urllib.parse.urlencode(q)}")


# ---------------------------------------------------------------- shaping

def _bare_doi(doi_url):
    if not doi_url:
        return None
    return doi_url.replace("https://doi.org/", "").replace(
        "http://doi.org/", "")


def _short_id(full_id):
    if not full_id:
        return None
    return full_id.rstrip("/").rsplit("/", 1)[-1]


def restore_abstract(inverted):
    """abstract_inverted_index {词: [位置,...]} -> 摘要全文。

    同一位置多词（罕见）时按词序拼接；位置缺口以空格补齐。
    """
    if not inverted:
        return None
    positions = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions.setdefault(i, []).append(word)
    if not positions:
        return None
    words = []
    for i in range(max(positions) + 1):
        words.extend(positions.get(i, []))
    return " ".join(words)


def shape_work(w, detail=False):
    authors = []
    for a in w.get("authorships") or []:
        au = a.get("author") or {}
        if au.get("display_name"):
            authors.append(au["display_name"])
    src = ((w.get("primary_location") or {}).get("source") or {})
    oa = w.get("open_access") or {}
    out = {"id": _short_id(w.get("id")),
           "title": w.get("display_name"),
           "year": w.get("publication_year"),
           "type": w.get("type"),
           "doi": _bare_doi(w.get("doi")),
           "authors": authors,
           "source": src.get("display_name"),
           "cited_by": w.get("cited_by_count"),
           "is_oa": oa.get("is_oa"),
           "oa_status": oa.get("oa_status"),
           "oa_url": oa.get("oa_url"),
           "url": w.get("id")}
    if detail:
        out["abstract"] = restore_abstract(w.get("abstract_inverted_index"))
        out["references"] = len(w.get("referenced_works") or [])
        out["language"] = w.get("language")
        out["fwci"] = w.get("fwci")
        topics = [t.get("display_name") for t in (w.get("topics") or [])
                  if t.get("display_name")]
        out["topics"] = topics[:5]
    return out


def shape_author(a):
    insts = [i.get("display_name")
             for i in a.get("last_known_institutions") or []
             if i.get("display_name")]
    return {"id": _short_id(a.get("id")),
            "name": a.get("display_name"),
            "works": a.get("works_count"),
            "cited_by": a.get("cited_by_count"),
            "institutions": insts,
            "orcid": (a.get("ids") or {}).get("orcid"),
            "url": a.get("id")}


# ---------------------------------------------------------------- commands

def cmd_search(args):
    data = api_get("/works", {"search": args.query,
                              "per-page": args.limit})
    meta = data.get("meta") or {}
    items = [shape_work(w) for w in data.get("results") or []]
    emit({"query": args.query, "total": meta.get("count"),
          "results": items}, args,
         cols=["id", "year", "title", "cited_by", "doi"])


def cmd_work(args):
    ref = str(args.ref).strip()
    if ref.startswith("10.") or ref.lower().startswith("doi:"):
        doi = ref[4:] if ref.lower().startswith("doi:") else ref
        path = f"/works/doi:{doi}"
    else:
        path = f"/works/{_short_id(ref)}"
    try:
        w = api_get(path)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            fail(f"找不到论文: {args.ref}", code="NOT_FOUND")
        raise
    if not w or not w.get("id"):
        fail(f"找不到论文: {args.ref}", code="NOT_FOUND")
    emit(shape_work(w, detail=True), args)


def cmd_author(args):
    data = api_get("/authors", {"search": args.name,
                                "per-page": args.limit})
    meta = data.get("meta") or {}
    items = [shape_author(a) for a in data.get("results") or []]
    emit({"query": args.name, "total": meta.get("count"),
          "results": items}, args,
         cols=["id", "name", "works", "cited_by"])


def cmd_doctor(args):
    checks = []
    for name, fn in (("works_search", lambda: api_get(
                         "/works", {"search": "test", "per-page": 1})),
                     ("work_detail", lambda: api_get(
                         "/works/doi:10.1038/nature14539")),
                     ("authors_search", lambda: api_get(
                         "/authors", {"search": "Bengio", "per-page": 1}))):
        t0 = time.time()
        try:
            r = fn()
            if not r:
                raise RuntimeError("空响应")
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
    {"name": "search", "usage": "openalex search <关键词> [--limit N]",
     "desc": "论文搜索（标题/摘要/作者全文检索）：年份/引用/DOI/期刊/开放获取"},
    {"name": "work", "usage": "openalex work <OpenAlex ID|DOI>",
     "desc": "论文详情：含由倒排索引还原的摘要全文、参考文献数、被引数"},
    {"name": "author", "usage": "openalex author <姓名> [--limit N]",
     "desc": "作者搜索：论文数/被引数/最近机构/ORCID"},
    {"name": "doctor", "usage": "openalex doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "openalex commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "引用计数为 OpenAlex 图谱口径，与 Google Scholar "
                         "不一致；错误带 code"}, args)


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
    p = argparse.ArgumentParser(
        prog="openalex", description="学术检索 CLI（OpenAlex，免密钥）")
    p.add_argument("--version", action="version",
                   version=f"openalex {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="论文搜索")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("work", help="论文详情（ID 或 DOI）")
    sp.add_argument("ref")
    sp.set_defaults(func=cmd_work)

    sp = sub.add_parser("author", help="作者搜索")
    sp.add_argument("name")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_author)

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
