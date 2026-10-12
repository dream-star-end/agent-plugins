#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pubmed — 生物医学文献检索 CLI（供 AI agent / 脚本调用）

数据源：NCBI E-utilities（PubMed，免费、无需密钥）
  * 检索 esearch.fcgi（db=pubmed，返回 PMID 列表与总数）
  * 摘要 esummary.fcgi（标题/期刊/日期/作者/DOI）
  * 详情 efetch.fcgi（XML：摘要全文 + MeSH 关键词）

边界：仅生物医学库；摘要为英文原文。无 API key 时 NCBI 限速约 3 次/秒，
本工具在请求间自动节流（≥0.4s 间隔）。

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
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
TIMEOUT = 25
VERSION = "1.0.0"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "agent-cli"
MIN_INTERVAL = 0.4  # 无密钥限速约 3 次/秒，留余量

_last_req = 0.0


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def _throttle():
    global _last_req
    wait = MIN_INTERVAL - (time.time() - _last_req)
    if wait > 0:
        time.sleep(wait)
    _last_req = time.time()


def _url(endpoint, params):
    q = {"tool": TOOL}
    q.update(params)
    return f"{EUTILS}/{endpoint}?" + urllib.parse.urlencode(q)


def http_text(url):
    last = None
    for attempt in range(3):
        _throttle()
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
            time.sleep(0.8 * (attempt + 1))
    raise last


def http_json(url):
    return json.loads(http_text(url))


def esearch(term, limit):
    data = http_json(_url("esearch.fcgi", {
        "db": "pubmed", "term": term, "retmode": "json",
        "retmax": limit, "sort": "relevance"}))
    r = data.get("esearchresult") or {}
    if r.get("errorlist"):
        fail(f"检索式错误: {r['errorlist']}", code="INVALID")
    return r.get("idlist") or [], int(r.get("count") or 0)


def esummary(pmids):
    if not pmids:
        return {}
    data = http_json(_url("esummary.fcgi", {
        "db": "pubmed", "id": ",".join(pmids), "retmode": "json"}))
    return data.get("result") or {}


def _doi_of(rec):
    for aid in rec.get("articleids") or []:
        if aid.get("idtype") == "doi":
            return aid.get("value")
    return None


def shape_summary(pmid, rec):
    authors = [a.get("name") for a in rec.get("authors") or []
               if a.get("name")]
    return {"pmid": pmid,
            "title": rec.get("title"),
            "journal": rec.get("fulljournalname") or rec.get("source"),
            "pubdate": rec.get("pubdate"),
            "authors": authors,
            "doi": _doi_of(rec),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}


def cmd_search(args):
    pmids, total = esearch(args.query, args.limit)
    result = esummary(pmids)
    items = [shape_summary(pmid, result[pmid]) for pmid in pmids
             if isinstance(result.get(pmid), dict)]
    emit({"query": args.query, "total": total, "returned": len(items),
          "results": items}, args,
         cols=["pmid", "title", "journal", "pubdate", "doi"])


def _text(elem):
    """取元素全文（含嵌套子标签，如标题里的斜体物种名）。"""
    if elem is None:
        return None
    s = "".join(elem.itertext()).strip()
    return s or None


def cmd_paper(args):
    pmid = str(args.pmid).strip()
    if not pmid.isdigit():
        fail(f"PMID 应为纯数字: {args.pmid}", code="INVALID")
    xml = http_text(_url("efetch.fcgi", {
        "db": "pubmed", "id": pmid, "retmode": "xml"}))
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        fail(f"efetch XML 解析失败: {e}", code="UPSTREAM")
    art = root.find(".//PubmedArticle")
    if art is None:
        fail(f"找不到文献 PMID {pmid}（可能不存在）", code="NOT_FOUND")
    title = _text(art.find(".//ArticleTitle"))
    # 摘要：多个 AbstractText 段（可带 Label，如 BACKGROUND/RESULTS）顺序拼接
    parts = []
    for ab in art.findall(".//Abstract/AbstractText"):
        label = ab.get("Label")
        txt = _text(ab)
        if txt:
            parts.append(f"{label}: {txt}" if label else txt)
    authors = []
    for au in art.findall(".//AuthorList/Author"):
        collective = _text(au.find("CollectiveName"))
        if collective:
            authors.append(collective)
            continue
        last = _text(au.find("LastName")) or ""
        init = _text(au.find("Initials")) or ""
        name = (last + " " + init).strip()
        if name:
            authors.append(name)
    mesh = []
    for mh in art.findall(".//MeshHeadingList/MeshHeading"):
        d = _text(mh.find("DescriptorName"))
        if d:
            mesh.append(d)
    pd = art.find(".//Journal/JournalIssue/PubDate")
    pubdate = None
    if pd is not None:
        pubdate = (_text(pd.find("MedlineDate"))
                   or " ".join(x for x in (_text(pd.find("Year")),
                                           _text(pd.find("Month")),
                                           _text(pd.find("Day"))) if x)
                   or None)
    doi = None
    for el in art.findall(".//ELocationID"):
        if el.get("EIdType") == "doi":
            doi = _text(el)
            break
    emit({"pmid": pmid, "title": title,
          "abstract": "\n".join(parts) or None,
          "authors": authors,
          "journal": _text(art.find(".//Journal/Title")),
          "pubdate": pubdate,
          "doi": doi,
          "mesh_terms": mesh,
          "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"}, args)


def cmd_doctor(args):
    checks = []
    for name, fn in (("esearch", lambda: esearch("cancer", 1)),
                     ("esummary", lambda: esummary(["35251086"])),
                     ("efetch", lambda: http_text(_url("efetch.fcgi", {
                         "db": "pubmed", "id": "35251086",
                         "retmode": "xml"})))):
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
    {"name": "search", "usage": "pubmed search <关键词> [--limit N]",
     "desc": "文献检索（相关度排序）：PMID/标题/期刊/日期/作者/DOI + 命中总数"},
    {"name": "paper", "usage": "pubmed paper <PMID>",
     "desc": "文献详情：标题/摘要全文/作者/期刊/日期/DOI/MeSH 关键词"},
    {"name": "doctor", "usage": "pubmed doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "pubmed commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "数据源 NCBI E-utilities（PubMed），免密钥；"
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
    p = argparse.ArgumentParser(prog="pubmed", description="生物医学文献检索 CLI（NCBI PubMed，免密钥）")
    p.add_argument("--version", action="version", version=f"pubmed {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="文献检索")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("paper", help="文献详情（含摘要全文）")
    sp.add_argument("pmid")
    sp.set_defaults(func=cmd_paper)

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
