#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fx — 汇率与数字资产行情 CLI（供 AI agent / 脚本调用）

数据源（公开接口，无需密钥）：
  * 法币汇率 Frankfurter（欧洲央行参考汇率，每日更新）：api.frankfurter.app
  * 加密货币 OKX 公开行情：okx.com/api/v5（Binance 公开接口对部分地区
    返回 451，故以 OKX 为主源）

默认 JSON 输出；全局 --table/--compact/--fields。错误带 code，退出码 1。
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
TIMEOUT = 20
VERSION = "1.0.0"


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


FIAT_NAMES = {"CNY": "人民币", "USD": "美元", "EUR": "欧元", "JPY": "日元",
              "GBP": "英镑", "HKD": "港币", "AUD": "澳元", "CAD": "加元",
              "CHF": "瑞郎", "KRW": "韩元", "SGD": "新加坡元", "TWD": "新台币",
              "THB": "泰铢", "NZD": "新西兰元", "INR": "印度卢比"}


def cmd_rate(args):
    base = args.base.upper()
    targets = [t.strip().upper() for t in args.to.split(",") if t.strip()]
    q = urllib.parse.urlencode({"from": base, "to": ",".join(targets)})
    data = http_json(f"https://api.frankfurter.app/latest?{q}")
    rates = data.get("rates") or {}
    if not rates:
        fail(f"无汇率数据: {base} -> {targets}", code="NOT_FOUND")
    rows = [{"base": base, "quote": k, "rate": v,
             "name": FIAT_NAMES.get(k), "date": data.get("date"),
             "converted": round(v * args.amount, 4) if args.amount else None}
            for k, v in rates.items()]
    emit({"base": base, "amount": args.amount, "date": data.get("date"),
          "source": "Frankfurter（欧洲央行参考汇率，日频）",
          "results": rows}, args, cols=["base", "quote", "rate", "converted"])


def cmd_currencies(args):
    data = http_json("https://api.frankfurter.app/currencies")
    rows = [{"code": k, "name": FIAT_NAMES.get(k) or v}
            for k, v in sorted(data.items())]
    emit({"count": len(rows), "results": rows}, args, cols=["code", "name"])


def okx_ticker(inst):
    q = urllib.parse.urlencode({"instId": inst})
    data = http_json(f"https://www.okx.com/api/v5/market/ticker?{q}")
    lst = data.get("data") or []
    if not lst:
        fail(f"无行情: {inst}（交易对不存在？）", code="NOT_FOUND")
    d = lst[0]

    def f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None
    open24, last = f(d.get("open24h")), f(d.get("last"))
    return {"inst": inst, "last": last, "bid": f(d.get("bidPx")),
            "ask": f(d.get("askPx")), "open24h": open24,
            "high24h": f(d.get("high24h")), "low24h": f(d.get("low24h")),
            "change24h_pct": round((last / open24 - 1) * 100, 3)
            if open24 and last else None,
            "vol24h": f(d.get("vol24h")), "vol_ccy24h": f(d.get("volCcy24h")),
            "ts": d.get("ts")}


def cmd_crypto(args):
    rows = []
    for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        inst = sym if "-" in sym else f"{sym}-USDT"
        try:
            rows.append(okx_ticker(inst))
        except SystemExit:
            raise
        except Exception as e:
            rows.append({"inst": inst, "error": str(e)[:120]})
    emit({"source": "OKX 公开行情", "results": rows}, args,
         cols=["inst", "last", "change24h_pct", "high24h", "low24h"])


def cmd_doctor(args):
    checks = []
    for name, fn in (("frankfurter", lambda: http_json(
            "https://api.frankfurter.app/latest?from=USD&to=CNY")),
            ("okx", lambda: okx_ticker("BTC-USDT"))):
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
    {"name": "rate", "usage": "fx rate USD [--to CNY,EUR] [--amount 100]",
     "desc": "法币汇率（欧洲央行日频参考汇率）+ 可选金额换算"},
    {"name": "currencies", "usage": "fx currencies", "desc": "支持的法币列表"},
    {"name": "crypto", "usage": "fx crypto BTC,ETH [--quote USDT]",
     "desc": "加密货币行情（OKX：现价/24h 涨跌/高低/量）"},
    {"name": "doctor", "usage": "fx doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "fx commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "法币为日频参考汇率（非实时中间价）；错误带 code"},
         args)


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
    p = argparse.ArgumentParser(prog="fx", description="汇率/加密行情 CLI（公开接口，免密钥）")
    p.add_argument("--version", action="version", version=f"fx {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("rate", help="法币汇率")
    sp.add_argument("base")
    sp.add_argument("--to", default="CNY")
    sp.add_argument("--amount", type=float, default=None)
    sp.set_defaults(func=cmd_rate)

    sp = sub.add_parser("currencies", help="支持的法币")
    sp.set_defaults(func=cmd_currencies)

    sp = sub.add_parser("crypto", help="加密货币行情（OKX）")
    sp.add_argument("symbols", help="逗号分隔，如 BTC,ETH 或 BTC-USDT")
    sp.set_defaults(func=cmd_crypto)

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
