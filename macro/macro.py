#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
macro — 世界银行宏观经济指标 CLI（供 AI agent / 脚本调用）

数据源：World Bank API v2（免费、无需密钥）
  * 指标数据 /v2/country/{国家}/indicator/{指标}（年度数据）
  * 国家列表 /v2/country（本地按名过滤）
  * 指标目录 /v2/indicator（全量 2 页拉取后本地缓存检索；
    官方 search 参数实测不生效，不依赖它）

默认 JSON 输出；--table 表格；--compact 单行；--fields 裁剪。
错误时 stderr 输出 {"error": ..., "code": ...} 且退出码 1。
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
TIMEOUT = 30
VERSION = "1.0.0"
API = "https://api.worldbank.org/v2"
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".macro_cache")
INDEX_FILE = os.path.join(CACHE_DIR, "indicators.json")
INDEX_TTL_DAYS = 30

PRESETS = [
    {"code": "NY.GDP.MKTP.CD", "name": "GDP（现价美元）",
     "use": "经济体量，跨国比较"},
    {"code": "NY.GDP.MKTP.KD.ZG", "name": "GDP 增速（年 %）",
     "use": "经济增长"},
    {"code": "NY.GDP.PCAP.CD", "name": "人均 GDP（现价美元）",
     "use": "发展水平"},
    {"code": "FP.CPI.TOTL.ZG", "name": "CPI 通胀率（年 %）",
     "use": "通货膨胀"},
    {"code": "SL.UEM.TOTL.ZS", "name": "失业率（占劳动力 %）",
     "use": "就业市场"},
    {"code": "SP.POP.TOTL", "name": "总人口", "use": "人口规模"},
    {"code": "SP.URB.TOTL.IN.ZS", "name": "城镇化率（%）",
     "use": "城市化"},
    {"code": "SP.DYN.LE00.IN", "name": "预期寿命（岁）",
     "use": "健康水平"},
    {"code": "NE.EXP.GNFS.ZS", "name": "出口占 GDP（%）",
     "use": "外需依赖"},
    {"code": "NE.IMP.GNFS.ZS", "name": "进口占 GDP（%）",
     "use": "开放度"},
    {"code": "BX.KLT.DINV.WD.GD.ZS", "name": "FDI 净流入占 GDP（%）",
     "use": "外资吸引力"},
    {"code": "GC.DOD.TOTL.GD.ZS", "name": "政府债务占 GDP（%）",
     "use": "财政风险"},
]


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


def _check_wb(data):
    """世行错误以 [{"message": [...]}] 返回，转成统一 fail。"""
    if isinstance(data, list) and data and isinstance(data[0], dict) \
            and "message" in data[0]:
        msgs = data[0].get("message") or []
        text = "; ".join(m.get("value", "") for m in msgs if isinstance(m, dict))
        fail(f"World Bank 参数错误: {text or 'invalid parameter'}",
             code="NOT_FOUND")
    return data


def wb_get(path, **params):
    params.setdefault("format", "json")
    q = urllib.parse.urlencode(params)
    return _check_wb(http_json(f"{API}/{path}?{q}"))


# ---------------------------------------------------------------- data

def cmd_data(args):
    country = args.country.strip().upper()
    indicator = args.indicator.strip().upper()
    y0, y1 = args.frm, args.to
    if y0 > y1:
        fail("--from 不能大于 --to", code="INVALID")
    data = wb_get(f"country/{country}/indicator/{indicator}",
                  per_page=200, date=f"{y0}:{y1}")
    meta, rows = (data + [None, []])[:2] if isinstance(data, list) \
        else ({}, [])
    rows = rows or []
    if not rows:
        fail(f"无数据: {country} / {indicator}（国家码或指标码可能不对，"
             "先用 macro country / macro indicator 查）", code="NOT_FOUND")
    series, null_years = [], []
    for r in rows:
        if r.get("value") is None:
            null_years.append(r.get("date"))
        else:
            series.append({"year": int(r["date"]), "value": r["value"]})
    series.sort(key=lambda x: x["year"])
    first = rows[0]
    emit({
        "country": (first.get("country") or {}).get("value"),
        "country_code": first.get("countryiso3code")
        or (first.get("country") or {}).get("id"),
        "indicator": (first.get("indicator") or {}).get("value"),
        "indicator_code": (first.get("indicator") or {}).get("id"),
        "unit": first.get("unit") or None,
        "source_last_updated": (meta or {}).get("lastupdated"),
        "latest": series[-1] if series else None,
        "points": len(series),
        "null_years": sorted(null_years, reverse=True),
        "series": series,
        "note": "年度数据；value 为空的年份已单列 null_years；"
                "世行数据会事后修订、最新年份常滞后 1-2 年",
    }, args, cols=["year", "value"])


# ---------------------------------------------------------------- country

def fetch_countries():
    data = wb_get("country", per_page=400)
    return data[1] or []


def cmd_country(args):
    kw = args.keyword.strip().lower()
    hits = []
    for c in fetch_countries():
        hay = " ".join(str(c.get(k) or "") for k in
                       ("id", "iso2Code", "name", "capitalCity")).lower()
        if kw in hay:
            hits.append({
                "code": c.get("id"), "iso2": c.get("iso2Code"),
                "name": c.get("name"), "capital": c.get("capitalCity"),
                "region": (c.get("region") or {}).get("value"),
                "income_level": (c.get("incomeLevel") or {}).get("value")})
    hits.sort(key=lambda x: (x["name"].lower() != kw,
                             not x["name"].lower().startswith(kw)))
    emit({"query": args.keyword, "count": len(hits),
          "results": hits[:args.limit]}, args,
         cols=["code", "iso2", "name", "capital", "region"])


# ---------------------------------------------------------------- indicator

def load_indicator_index():
    """全量指标目录（约 2.9 万条，2 页）本地缓存 30 天，供本地检索。"""
    if os.path.exists(INDEX_FILE):
        try:
            age = time.time() - os.path.getmtime(INDEX_FILE)
            if age < INDEX_TTL_DAYS * 86400:
                with open(INDEX_FILE, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
    items, page = [], 1
    while True:
        data = wb_get("indicator", per_page=20000, page=page)
        meta, rows = data[0], data[1] or []
        items.extend({"code": r.get("id"), "name": r.get("name"),
                      "unit": r.get("unit") or None,
                      "source": (r.get("source") or {}).get("value")}
                     for r in rows)
        if page >= int(meta.get("pages", 1)):
            break
        page += 1
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
    except Exception:
        pass
    return items


def cmd_indicator(args):
    kw_raw = args.keyword.strip()
    kw = kw_raw.lower()
    # 像指标码（大写字母数字+点）先精确查
    if re.fullmatch(r"[A-Za-z0-9]+(\.[A-Za-z0-9]+)+", kw_raw):
        try:
            data = wb_get(f"indicator/{kw_raw.upper()}")
            rows = data[1] or []
            if rows:
                r = rows[0]
                emit({"query": kw_raw, "exact": True,
                      "results": [{"code": r.get("id"),
                                   "name": r.get("name"),
                                   "unit": r.get("unit") or None,
                                   "source": (r.get("source") or {}).get(
                                       "value"),
                                   "note": (r.get("sourceNote") or "")[:300]
                                   or None}]}, args,
                     cols=["code", "name", "unit", "source"])
                return
        except SystemExit:
            raise
        except Exception:
            pass
    index = load_indicator_index()
    hits = []
    for it in index:
        name = (it.get("name") or "").lower()
        code = (it.get("code") or "").lower()
        if kw in name or kw in code:
            rank = 0 if code == kw else 1 if code.startswith(kw) \
                else 2 if name.startswith(kw) else 3
            hits.append((rank, it))
    hits.sort(key=lambda x: (x[0], x[1].get("name") or ""))
    emit({"query": kw_raw, "index_size": len(index),
          "count": len(hits),
          "results": [h[1] for h in hits[:args.limit]]}, args,
         cols=["code", "name", "unit", "source"])


# ---------------------------------------------------------------- presets

def cmd_presets(args):
    emit({"results": PRESETS,
          "usage": "macro data <国家码> <指标码>，如 macro data CHN NY.GDP.MKTP.CD；"
                   "更多指标用 macro indicator <关键词> 搜"},
         args, cols=["code", "name", "use"])


# ---------------------------------------------------------------- doctor

def cmd_doctor(args):
    checks = []

    def probe_data():
        d = wb_get("country/CHN/indicator/NY.GDP.MKTP.CD",
                   per_page=1, date="2024:2026")
        if not (d[1] and d[1][0].get("value") is not None):
            raise RuntimeError("数据为空")

    for name, fn in (("country_list", fetch_countries),
                     ("indicator_data", probe_data),
                     ("indicator_exact", lambda: wb_get(
                         "indicator/FP.CPI.TOTL.ZG"))):
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
    {"name": "data", "usage": "macro data <国家码> <指标码> [--from 年] [--to 年]",
     "desc": "某国某指标的年度时间序列（含最新值、空值年份标注）"},
    {"name": "country", "usage": "macro country <关键词>",
     "desc": "按名称/代码搜国家（返回 ISO3/ISO2 代码、首都、地区）"},
    {"name": "indicator", "usage": "macro indicator <关键词|指标码>",
     "desc": "搜指标：给码精确查，给词查本地全量目录（约 2.9 万条）"},
    {"name": "presets", "usage": "macro presets",
     "desc": "常用宏观指标速查表（GDP/增速/CPI/失业率/人口/出口等）"},
    {"name": "doctor", "usage": "macro doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "macro commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "数据为年度频率（World Bank WDI 等），"
                         "最新年份通常滞后 1-2 年且事后可修订；错误带 code"},
         args)


# ---------------------------------------------------------------- output

_LIST_KEYS = ("results", "checks", "series")


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
        prog="macro", description="宏观经济指标 CLI（World Bank，免密钥）")
    p.add_argument("--version", action="version", version=f"macro {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("data", help="国家指标时间序列")
    sp.add_argument("country")
    sp.add_argument("indicator")
    sp.add_argument("--from", dest="frm", type=int, default=2000)
    sp.add_argument("--to", type=int, default=2026)
    sp.set_defaults(func=cmd_data)

    sp = sub.add_parser("country", help="搜国家代码")
    sp.add_argument("keyword")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_country)

    sp = sub.add_parser("indicator", help="搜指标 / 精确查指标")
    sp.add_argument("keyword")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_indicator)

    sp = sub.add_parser("presets", help="常用指标速查")
    sp.set_defaults(func=cmd_presets)

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
