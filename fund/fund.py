#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fund — 公募基金查询 CLI（供 AI agent / 脚本调用）

数据源：天天基金 / 东方财富公开接口（无需密钥）
  * 全量基金索引 fund.eastmoney.com/js/fundcode_search.js（本地缓存 7 天）
  * 历史净值    api.fund.eastmoney.com/f10/lsjz
  * 基金资料    fund.eastmoney.com/pingzhongdata/{code}.js
  * 持仓明细    fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc
  * 收益排行    fund.eastmoney.com/data/rankhandler.aspx

注意：老牌盘中估值接口 fundgz 已下线，本工具只提供日终官方净值，不编造估值。
默认 JSON 输出；全局 --table/--compact/--fields。错误带 code，退出码 1。
仅使用 Python 标准库。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
TIMEOUT = 25
VERSION = "1.0.0"
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".fund_cache")
REFERER = {"Referer": "https://fund.eastmoney.com/"}


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def http_get(url, referer=True):
    headers = {"User-Agent": UA}
    if referer:
        headers.update(REFERER)
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (502, 503, 504):
                raise
        except urllib.error.URLError as e:
            last = e
        if attempt < 2:
            time.sleep(0.7 * (attempt + 1))
    raise last


def http_json(url):
    return json.loads(http_get(url))


# ---------------------------------------------------------------- search index

def load_search_index():
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, "fundcode_search.json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < 7 * 86400:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    text = http_get("https://fund.eastmoney.com/js/fundcode_search.js")
    m = re.search(r"var r = (\[.*\]);?\s*$", text, re.S)
    if not m:
        raise RuntimeError("基金索引解析失败")
    rows = json.loads(m.group(1))
    index = [{"code": r[0], "abbr": r[1], "name": r[2], "type": r[3],
              "pinyin": r[4]} for r in rows]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    return index


def cmd_search(args):
    kw = args.keyword.strip()
    index = load_search_index()
    hits = []
    for it in index:
        if (kw in it["name"] or kw.lower() in it["pinyin"].lower()
                or kw in it["code"] or kw.lower() in it["abbr"].lower()):
            hits.append(it)
    hits.sort(key=lambda x: (x["code"] != kw, not x["name"].startswith(kw)))
    emit({"keyword": kw, "total_index": len(index), "count": len(hits),
          "results": hits[:args.limit]}, args,
         cols=["code", "name", "type"])


# ---------------------------------------------------------------- nav / info

def fetch_lsjz(code, limit):
    q = urllib.parse.urlencode({"fundCode": code, "pageIndex": 1,
                                "pageSize": limit})
    data = http_json(f"https://api.fund.eastmoney.com/f10/lsjz?{q}")
    lst = (data.get("Data") or {}).get("LSJZList") or []
    return [{"date": r["FSRQ"], "nav": float(r["DWJZ"]) if r["DWJZ"] else None,
             "acc_nav": float(r["LJJZ"]) if r["LJJZ"] else None,
             "change_pct": float(r["JZZZL"]) if r["JZZZL"] else None,
             "buy_status": r.get("SGZT"), "sell_status": r.get("SHZT"),
             "dividend": r.get("FHSP") or None} for r in lst]


def cmd_nav(args):
    rows = fetch_lsjz(args.code, args.limit)
    if not rows:
        fail(f"无净值数据（代码不存在？）: {args.code}", code="NOT_FOUND")
    emit({"code": args.code, "latest": rows[0], "history": rows}, args,
         cols=["date", "nav", "acc_nav", "change_pct"])


def _js_var(text, name):
    m = re.search(rf"var {name}\s*=\s*\"([^\"]*)\"", text)
    return m.group(1) if m else None


def cmd_info(args):
    text = http_get(f"https://fund.eastmoney.com/pingzhongdata/{args.code}.js")
    if "fS_code" not in text:
        fail(f"基金不存在: {args.code}", code="NOT_FOUND")
    codes_m = re.search(r"var stockCodes=\[(.*?)\];", text, re.S)
    holdings = []
    if codes_m:
        for raw in re.findall(r'"(\d{6})(\d)"', codes_m.group(1)):
            holdings.append({"code": raw[0],
                             "market": "SH" if raw[1] == "1" else "SZ"})
    alloc = {}
    am = re.search(r"var Data_assetAllocation = (\{.*?\});", text, re.S)
    if am:
        try:
            obj = json.loads(am.group(1))
            for s in obj.get("series", []):
                if s.get("data"):
                    alloc[s["name"]] = s["data"][-1]
        except Exception:
            pass
    nav = fetch_lsjz(args.code, 1)
    emit({"code": args.code, "name": _js_var(text, "fS_name"),
          "rate_current": _js_var(text, "fund_Rate"),
          "rate_source": _js_var(text, "fund_sourceRate"),
          "min_purchase": _js_var(text, "fund_minsg"),
          # pingzhongdata 变量名后缀：n=年、y=月（syl_1n 近1年、syl_1y 近1月）
          "returns_pct": {"m1": _js_var(text, "syl_1y"),
                          "m3": _js_var(text, "syl_3y"),
                          "m6": _js_var(text, "syl_6y"),
                          "y1": _js_var(text, "syl_1n")},
          "asset_allocation_latest": alloc,
          "holdings_codes_top10": holdings,
          "latest_nav": nav[0] if nav else None}, args)


def cmd_holdings(args):
    q = urllib.parse.urlencode({"type": "jjcc", "code": args.code,
                                "topline": args.limit})
    text = http_get(f"https://fundf10.eastmoney.com/FundArchivesDatas.aspx?{q}")
    cm = re.search(r'content:"(.*?)",arryear', text, re.S)
    if not cm:
        fail(f"无持仓数据: {args.code}", code="NOT_FOUND")
    content = cm.group(1).encode().decode("unicode_escape", errors="ignore") \
        if "\\u" in cm.group(1) else cm.group(1)
    qm = re.search(r"(\d{4})年(\d)季度股票投资明细", content)
    dm = re.search(r"截止至：<font[^>]*>(\d{4}-\d{2}-\d{2})</font>", content)
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", content, re.S):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        code_i = next((i for i, c in enumerate(cells)
                       if re.fullmatch(r"\d{6}", c)), None)
        if code_i is None:
            continue
        pct = next((c for c in cells if re.fullmatch(r"\d+\.\d+%", c)), None)
        nums = [c for c in cells if re.fullmatch(r"[\d,]+(\.\d+)?", c)]
        rows.append({"code": cells[code_i],
                     "name": cells[code_i + 1] if code_i + 1 < len(cells) else "",
                     "pct_of_nav": pct,
                     "shares_wan": nums[-2] if len(nums) >= 2 else None,
                     "value_wan": nums[-1] if nums else None})
    emit({"code": args.code,
          "quarter": f"{qm.group(1)}Q{qm.group(2)}" if qm else None,
          "as_of": dm.group(1) if dm else None,
          "holdings": rows[:args.limit]}, args,
         cols=["code", "name", "pct_of_nav", "shares_wan", "value_wan"])


# ---------------------------------------------------------------- rank

RANK_TYPES = {"all": "all", "gp": "gp", "hh": "hh", "zq": "zq",
              "zs": "zs", "qdii": "qdii", "fof": "fof"}
RANK_BY = {"day": "rzdf", "week": "zzf", "m1": "1yzf", "m3": "3yzf",
           "m6": "6yzf", "y1": "1nzf", "y2": "2nzf", "y3": "3nzf",
           "ytd": "jnzf"}


def cmd_rank(args):
    q = urllib.parse.urlencode({
        "op": "ph", "dt": "kf", "ft": RANK_TYPES[args.type], "rs": "",
        "gs": 0, "sc": RANK_BY[args.by], "st": "desc", "pi": 1,
        "pn": args.limit, "dx": 1})
    text = http_get(f"https://fund.eastmoney.com/data/rankhandler.aspx?{q}")
    m = re.search(r"datas:\[(.*?)\]\s*,", text, re.S)
    if not m:
        fail("排行解析失败", code="UPSTREAM")
    rows = []
    for item in re.findall(r'"([^"]*)"', m.group(1)):
        f = item.split(",")
        if len(f) < 16:
            continue

        def fv(x):
            try:
                return float(x)
            except ValueError:
                return None
        rows.append({"code": f[0], "name": f[1], "date": f[3],
                     "nav": fv(f[4]), "acc_nav": fv(f[5]),
                     "day_pct": fv(f[6]), "week_pct": fv(f[7]),
                     "m1_pct": fv(f[8]), "m3_pct": fv(f[9]),
                     "m6_pct": fv(f[10]), "y1_pct": fv(f[11]),
                     "y2_pct": fv(f[12]), "y3_pct": fv(f[13]),
                     "ytd_pct": fv(f[14]), "since_pct": fv(f[15]),
                     "inception": f[16] if len(f) > 16 else None})
    emit({"type": args.type, "by": args.by, "results": rows}, args,
         cols=["code", "name", "nav", "day_pct", "y1_pct", "ytd_pct"])


def cmd_doctor(args):
    checks = []
    for name, fn in (("search_index", lambda: load_search_index()),
                     ("lsjz", lambda: fetch_lsjz("161725", 1)),
                     ("pingzhongdata", lambda: http_get(
                         "https://fund.eastmoney.com/pingzhongdata/161725.js")),
                     ("rank", lambda: http_get(
                         "https://fund.eastmoney.com/data/rankhandler.aspx"
                         "?op=ph&dt=kf&ft=all&sc=1nzf&st=desc&pi=1&pn=1&dx=1"))):
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
    {"name": "search", "usage": "fund search <关键词> [--limit N]",
     "desc": "按名称/拼音/代码搜基金（全量索引本地缓存 7 天）"},
    {"name": "nav", "usage": "fund nav <代码> [--limit N]",
     "desc": "历史净值（日终官方净值、涨跌幅、申赎状态）"},
    {"name": "info", "usage": "fund info <代码>",
     "desc": "基金资料：费率/最低申购/阶段收益/资产配置/前十大持仓代码/最新净值"},
    {"name": "holdings", "usage": "fund holdings <代码> [--limit N]",
     "desc": "最新季报持仓明细（股票、占净值比、持股数、市值）"},
    {"name": "rank", "usage": "fund rank [--type all|gp|hh|zq|zs|qdii|fof] "
     "[--by day|week|m1|m3|m6|y1|y2|y3|ytd] [--limit N]",
     "desc": "收益排行（天天基金排行口径）"},
    {"name": "doctor", "usage": "fund doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "fund commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "只有日终官方净值，无盘中估值（老接口已下线）；"
                         "错误带 code"}, args)


# ---------------------------------------------------------------- output

_LIST_KEYS = ("results", "history", "holdings", "checks")


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
    p = argparse.ArgumentParser(prog="fund", description="公募基金 CLI（天天基金/东方财富公开接口）")
    p.add_argument("--version", action="version", version=f"fund {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="搜基金（名称/拼音/代码）")
    sp.add_argument("keyword")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("nav", help="历史净值")
    sp.add_argument("code")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_nav)

    sp = sub.add_parser("info", help="基金资料 + 阶段收益 + 持仓代码")
    sp.add_argument("code")
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("holdings", help="季报持仓明细")
    sp.add_argument("code")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_holdings)

    sp = sub.add_parser("rank", help="收益排行")
    sp.add_argument("--type", default="all", choices=list(RANK_TYPES))
    sp.add_argument("--by", default="y1", choices=list(RANK_BY))
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_rank)

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
