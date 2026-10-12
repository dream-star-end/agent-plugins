#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weather — 天气查询 CLI（供 AI agent / 脚本调用）

数据源：Open-Meteo（免费、无需密钥）
  * 地理编码 geocoding-api.open-meteo.com
  * 预报    api.open-meteo.com
  * 空气质量 air-quality-api.open-meteo.com

默认 JSON 输出；--table 表格；--compact 单行；--fields 裁剪。
错误时 stderr 输出 {"error": ..., "code": ...} 且退出码 1。
仅使用 Python 标准库。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
TIMEOUT = 20
VERSION = "1.0.0"

WMO = {
    0: "晴", 1: "多云", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "毛毛雨(弱)", 53: "毛毛雨", 55: "毛毛雨(强)",
    56: "冻毛毛雨(弱)", 57: "冻毛毛雨(强)",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨(弱)", 67: "冻雨(强)",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨(弱)", 81: "阵雨", 82: "暴雨",
    85: "阵雪(弱)", 86: "阵雪(强)",
    95: "雷阵雨", 96: "雷阵雨伴冰雹(弱)", 99: "雷阵雨伴冰雹(强)",
}


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def http_json(url):
    import time
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


def geocode(city, count=5):
    q = urllib.parse.urlencode({"name": city, "count": count,
                                "language": "zh", "format": "json"})
    data = http_json(f"https://geocoding-api.open-meteo.com/v1/search?{q}")
    return data.get("results") or []


def resolve_place(query):
    """城市名 -> 地点；也支持 'lat,lon' 直给坐标。"""
    s = str(query).strip()
    if "," in s:
        a, b = s.split(",", 1)
        try:
            return {"name": s, "latitude": float(a), "longitude": float(b),
                    "timezone": "auto", "country": "", "admin1": ""}
        except ValueError:
            pass
    results = geocode(s, count=1)
    if not results:
        fail(f"找不到城市: {query}", code="NOT_FOUND")
    r = results[0]
    return {"name": r.get("name"), "latitude": r.get("latitude"),
            "longitude": r.get("longitude"), "timezone": r.get("timezone"),
            "country": r.get("country", ""), "admin1": r.get("admin1", "")}


def _wmo(code):
    return WMO.get(code, f"未知({code})")


def fetch_forecast(place, days):
    q = urllib.parse.urlencode({
        "latitude": place["latitude"], "longitude": place["longitude"],
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                   "weather_code,wind_speed_10m,wind_direction_10m,"
                   "surface_pressure,precipitation",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "sunrise,sunset,precipitation_sum,"
                 "precipitation_probability_max,wind_speed_10m_max,uv_index_max",
        "timezone": place.get("timezone") or "auto",
        "forecast_days": days,
    })
    return http_json(f"https://api.open-meteo.com/v1/forecast?{q}")


def shape_current(fc):
    c = fc.get("current", {})
    return {"time": c.get("time"), "temp_c": c.get("temperature_2m"),
            "feels_like_c": c.get("apparent_temperature"),
            "humidity_pct": c.get("relative_humidity_2m"),
            "weather": _wmo(c.get("weather_code")),
            "weather_code": c.get("weather_code"),
            "wind_kmh": c.get("wind_speed_10m"),
            "wind_dir_deg": c.get("wind_direction_10m"),
            "pressure_hpa": c.get("surface_pressure"),
            "precipitation_mm": c.get("precipitation")}


def shape_daily(fc):
    d = fc.get("daily", {})
    out = []
    for i, date in enumerate(d.get("time", [])):
        out.append({
            "date": date,
            "weather": _wmo(d["weather_code"][i]),
            "temp_max_c": d["temperature_2m_max"][i],
            "temp_min_c": d["temperature_2m_min"][i],
            "precipitation_mm": (d.get("precipitation_sum") or [None])[i],
            "precip_prob_max_pct": (d.get("precipitation_probability_max")
                                    or [None])[i],
            "wind_max_kmh": (d.get("wind_speed_10m_max") or [None])[i],
            "uv_index_max": (d.get("uv_index_max") or [None])[i],
            "sunrise": (d.get("sunrise") or [None])[i],
            "sunset": (d.get("sunset") or [None])[i],
        })
    return out


def base_payload(place, fc):
    return {"place": {"name": place["name"], "admin1": place.get("admin1"),
                      "country": place.get("country"),
                      "latitude": place["latitude"],
                      "longitude": place["longitude"]},
            "timezone": fc.get("timezone")}


def cmd_now(args):
    place = resolve_place(args.city)
    fc = fetch_forecast(place, days=1)
    out = base_payload(place, fc)
    out["current"] = shape_current(fc)
    daily = shape_daily(fc)
    out["today"] = daily[0] if daily else None
    emit(out, args)


def cmd_forecast(args):
    place = resolve_place(args.city)
    fc = fetch_forecast(place, days=args.days)
    out = base_payload(place, fc)
    out["current"] = shape_current(fc)
    out["daily"] = shape_daily(fc)
    emit(out, args, cols=["date", "weather", "temp_min_c", "temp_max_c",
                          "precip_prob_max_pct", "precipitation_mm"])


def cmd_air(args):
    place = resolve_place(args.city)
    q = urllib.parse.urlencode({
        "latitude": place["latitude"], "longitude": place["longitude"],
        "current": "us_aqi,european_aqi,pm2_5,pm10,carbon_monoxide,"
                   "nitrogen_dioxide,ozone",
        "timezone": place.get("timezone") or "auto"})
    data = http_json(f"https://air-quality-api.open-meteo.com/v1/air-quality?{q}")
    c = data.get("current", {})
    aqi = c.get("us_aqi")
    level = None
    if aqi is not None:
        level = ("优" if aqi <= 50 else "良" if aqi <= 100 else
                 "轻度污染" if aqi <= 150 else "中度污染" if aqi <= 200 else
                 "重度污染" if aqi <= 300 else "严重污染")
    emit({"place": {"name": place["name"], "admin1": place.get("admin1"),
                    "latitude": place["latitude"],
                    "longitude": place["longitude"]},
          "time": c.get("time"), "aqi_us": aqi, "aqi_level": level,
          "aqi_eu": c.get("european_aqi"),
          "pm2_5": c.get("pm2_5"), "pm10": c.get("pm10"),
          "co": c.get("carbon_monoxide"), "no2": c.get("nitrogen_dioxide"),
          "o3": c.get("ozone"),
          "note": "AQI 为模型估算值（CAMS），非监测站实测"}, args)


def cmd_search(args):
    results = geocode(args.city, count=args.limit)
    items = [{"name": r.get("name"), "admin1": r.get("admin1"),
              "country": r.get("country"), "latitude": r.get("latitude"),
              "longitude": r.get("longitude"),
              "timezone": r.get("timezone"),
              "population": r.get("population")} for r in results]
    emit({"query": args.city, "results": items}, args,
         cols=["name", "admin1", "country", "latitude", "longitude"])


def cmd_doctor(args):
    import time
    checks = []
    for name, fn in (("geocoding", lambda: geocode("北京", 1)),
                     ("forecast", lambda: fetch_forecast(
                         {"latitude": 39.9, "longitude": 116.4,
                          "timezone": "Asia/Shanghai"}, 1)),
                     ("air_quality", lambda: http_json(
                         "https://air-quality-api.open-meteo.com/v1/"
                         "air-quality?latitude=39.9&longitude=116.4"
                         "&current=us_aqi"))):
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
    {"name": "now", "usage": "weather now <城市>", "desc": "当前天气 + 今日概览"},
    {"name": "forecast", "usage": "weather forecast <城市> [--days 1-16]",
     "desc": "逐日预报（气温/降水概率/风/紫外线/日出日落）"},
    {"name": "air", "usage": "weather air <城市>",
     "desc": "空气质量 AQI/PM2.5（模型估算，非实测）"},
    {"name": "search", "usage": "weather search <城市名>",
     "desc": "城市消歧（返回候选地点与经纬度）"},
    {"name": "doctor", "usage": "weather doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "weather commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "城市可用中文名或 'lat,lon'；错误带 code"}, args)


# ---------------------------------------------------------------- output

_LIST_KEYS = ("results", "daily", "checks")


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
    p = argparse.ArgumentParser(prog="weather", description="天气 CLI（Open-Meteo，免密钥）")
    p.add_argument("--version", action="version", version=f"weather {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("now", help="当前天气")
    sp.add_argument("city")
    sp.set_defaults(func=cmd_now)

    sp = sub.add_parser("forecast", help="逐日预报")
    sp.add_argument("city")
    sp.add_argument("--days", type=int, default=7)
    sp.set_defaults(func=cmd_forecast)

    sp = sub.add_parser("air", help="空气质量")
    sp.add_argument("city")
    sp.set_defaults(func=cmd_air)

    sp = sub.add_parser("search", help="城市搜索/消歧")
    sp.add_argument("city")
    sp.add_argument("--limit", type=int, default=5)
    sp.set_defaults(func=cmd_search)

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
