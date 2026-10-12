#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stooq — 全球行情查询 CLI（供 AI agent / 脚本调用）

数据源：Stooq（免费、无需密钥）
  * 报价   stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv
  * 日线   stooq.com/q/d/l/?s={symbol}&i=d

symbol 形如 aapl.us（美股）、^spx / ^dji（指数）、eurusd（外汇）、
xauusd（黄金）、cl.f（原油期货）、spy.us（ETF）。

数据口径：Stooq 免费数据多为日线/延迟行情，不是实时 tick；
美股为收盘价或延迟价。报价 CSV 无昨收字段，涨跌额/幅按
「收盘价 − 当日开盘价」计算，输出中已标注。

默认 JSON 输出；--table 表格；--compact 单行；--fields 裁剪。
错误时 stderr 输出 {"error": ..., "code": ...} 且退出码 1。
仅使用 Python 标准库。
"""
import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
TIMEOUT = 25
VERSION = "1.0.0"

QUOTE_URL = "https://stooq.com/q/l/?s={s}&f=sd2t2ohlcv&h&e=csv"
HIST_URL = "https://stooq.com/q/d/l/?s={s}&i=d"

NOTE_QUOTE = ("涨跌额/幅 = 收盘价 − 当日开盘价（Stooq 报价 CSV 无昨收字段）；"
              "数据为日线/延迟行情，非实时 tick，美股为收盘或延迟价")
NOTE_HIST = ("日线 OHLCV（Stooq 免费数据）；区间涨跌 = 窗口末日收盘 − 首日收盘；"
             "数据可能延迟，非实时行情")


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
            if e.code not in (502, 503, 504):
                raise
        except urllib.error.URLError as e:
            last = e
        if attempt < 2:
            time.sleep(0.7 * (attempt + 1))
    raise last


def _num(s):
    """CSV 数值字段 -> float；空或 'N/D' -> None。"""
    if s is None:
        return None
    s = s.strip()
    if not s or s.upper() == "N/D":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _vol(s):
    v = _num(s)
    return int(v) if v is not None else None


def _check_csv(text, header):
    """Stooq 出错/限流时返回 HTML 页而非 CSV，这里拦截并如实报错。"""
    if text.lstrip().startswith(header):
        return
    if "does not exist" in text:
        fail("Stooq 返回 'page does not exist'：symbol 不存在，"
             "或该 IP 的免费 CSV 请求已被限流", code="NOT_FOUND")
    if "verify your browser" in text or "__verify" in text:
        fail("Stooq 触发了浏览器验证（反爬/限流），稍后再试", code="BLOCKED")
    fail(f"Stooq 返回非 CSV 内容: {text[:120]!r}", code="UPSTREAM")


def fetch_quote(symbols):
    s = ",".join(symbols)
    url = QUOTE_URL.format(s=urllib.parse.quote(s, safe=",^"))
    text = http_text(url)
    _check_csv(text, "Symbol,")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        o, c = _num(row.get("Open")), _num(row.get("Close"))
        change = pct = None
        if o is not None and c is not None:
            change = round(c - o, 4)
            if o:
                pct = round((c - o) / o * 100, 2)
        rows.append({"symbol": row.get("Symbol"),
                     "date": row.get("Date"), "time": row.get("Time"),
                     "open": o, "high": _num(row.get("High")),
                     "low": _num(row.get("Low")), "close": c,
                     "change": change, "change_pct": pct,
                     "volume": _vol(row.get("Volume"))})
    return rows


def fetch_history(symbol):
    url = HIST_URL.format(s=urllib.parse.quote(symbol, safe="^"))
    text = http_text(url)
    _check_csv(text, "Date,")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        rows.append({"date": row.get("Date"),
                     "open": _num(row.get("Open")),
                     "high": _num(row.get("High")),
                     "low": _num(row.get("Low")),
                     "close": _num(row.get("Close")),
                     "volume": _vol(row.get("Volume"))})
    return [r for r in rows if r["date"]]


def cmd_quote(args):
    symbols = [s.strip().lower() for s in args.symbols if s.strip()]
    if not symbols:
        fail("至少给一个 symbol", code="INVALID")
    rows = fetch_quote(symbols)
    bad = [r["symbol"] for r in rows if r["close"] is None]
    if bad:
        fail(f"无报价数据（symbol 可能不存在）: {', '.join(bad)}",
             code="NOT_FOUND")
    emit({"source": "Stooq", "note": NOTE_QUOTE, "results": rows}, args,
         cols=["symbol", "date", "open", "high", "low", "close",
               "change", "change_pct", "volume"])


def cmd_history(args):
    if args.days < 1:
        fail("--days 须 >= 1", code="INVALID")
    symbol = args.symbol.strip().lower()
    all_rows = fetch_history(symbol)
    if not all_rows:
        fail(f"无历史数据: {symbol}（symbol 可能不存在）", code="NOT_FOUND")
    rows = all_rows[-args.days:]
    first, last = rows[0], rows[-1]
    change = pct = None
    if first["close"] is not None and last["close"] is not None:
        change = round(last["close"] - first["close"], 4)
        if first["close"]:
            pct = round((last["close"] - first["close"])
                        / first["close"] * 100, 2)
    emit({"source": "Stooq", "symbol": symbol.upper(),
          "total_rows": len(all_rows),
          "range": {"first_date": all_rows[0]["date"],
                    "last_date": all_rows[-1]["date"]},
          "period": {"days": len(rows),
                     "first_close": first["close"],
                     "last_close": last["close"],
                     "change": change, "change_pct": pct},
          "note": NOTE_HIST, "rows": rows}, args,
         cols=["date", "open", "high", "low", "close", "volume"])


def cmd_doctor(args):
    checks = []
    for name, fn in (("quote_csv", lambda: fetch_quote(["aapl.us"])),
                     ("history_csv", lambda: fetch_history("aapl.us"))):
        t0 = time.time()
        try:
            r = fn()
            if not r:
                raise RuntimeError("返回为空")
            checks.append({"name": name, "ok": True,
                           "ms": int((time.time() - t0) * 1000)})
        except SystemExit:
            checks.append({"name": name, "ok": False,
                           "ms": int((time.time() - t0) * 1000),
                           "detail": "Stooq 返回错误页（可能限流）"})
        except Exception as e:
            checks.append({"name": name, "ok": False,
                           "ms": int((time.time() - t0) * 1000),
                           "detail": str(e)[:160]})
    ok = all(c["ok"] for c in checks)
    emit({"ok": ok, "checks": checks}, args)
    if not ok:
        sys.exit(1)


COMMANDS_MANIFEST = [
    {"name": "quote", "usage": "stooq quote <symbol...>",
     "desc": "报价（可多 symbol）：OHLCV + 当日涨跌（收盘−开盘口径），"
             "如 aapl.us、^spx、eurusd、xauusd、cl.f"},
    {"name": "history", "usage": "stooq history <symbol> [--days N]",
     "desc": "最近 N 日日线 OHLCV + 区间涨跌（默认 30 日）"},
    {"name": "doctor", "usage": "stooq doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "stooq commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "数据为 Stooq 日线/延迟行情，非实时 tick；"
                         "错误带 code"}, args)


# ---------------------------------------------------------------- output

_LIST_KEYS = ("results", "rows", "checks")


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
        prog="stooq", description="全球行情 CLI（Stooq，免密钥，日线/延迟数据）")
    p.add_argument("--version", action="version", version=f"stooq {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("quote", help="报价（可多 symbol）")
    sp.add_argument("symbols", nargs="+")
    sp.set_defaults(func=cmd_quote)

    sp = sub.add_parser("history", help="日线历史")
    sp.add_argument("symbol")
    sp.add_argument("--days", type=int, default=30)
    sp.set_defaults(func=cmd_history)

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
