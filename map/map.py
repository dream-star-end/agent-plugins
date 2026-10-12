#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
map — 地图与出行 CLI（供 AI agent / 脚本调用）

数据源（OpenStreetMap 生态，免费、无需密钥）：
  * 地理编码/逆编码 Nominatim（nominatim.openstreetmap.org）
  * 路线规划 OSRM（routing.openstreetmap.de，驾车/步行/骑行）
  * 周边 POI Overpass API（overpass-api.de）

默认 JSON 输出；全局 --table/--compact/--fields。错误带 code，退出码 1。
仅使用 Python 标准库。注意 Nominatim 政策要求低频使用，本工具为单次查询。
"""
import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "agent-map-cli/1.0 (personal assistant; contact via github dream-star-end)"
TIMEOUT = 30
VERSION = "1.0.0"
NOMINATIM = "https://nominatim.openstreetmap.org"
# Overpass 公共实例负载波动大：多镜像顺序兜底（lz4 变体实测最快）
OVERPASS_MIRRORS = ["https://lz4.overpass-api.de/api/interpreter",
                    "https://overpass-api.de/api/interpreter"]
OSRM_PROFILES = {"driving": "routed-car", "walking": "routed-foot",
                 "cycling": "routed-bike"}

POI_TYPES = {
    "餐厅": ("amenity", "restaurant"), "咖啡": ("amenity", "cafe"),
    "快餐": ("amenity", "fast_food"), "酒吧": ("amenity", "bar"),
    "酒店": ("tourism", "hotel"), "景点": ("tourism", "attraction"),
    "博物馆": ("tourism", "museum"), "医院": ("amenity", "hospital"),
    "药店": ("amenity", "pharmacy"), "诊所": ("amenity", "clinic"),
    "加油站": ("amenity", "fuel"), "充电站": ("amenity", "charging_station"),
    "停车场": ("amenity", "parking"), "银行": ("amenity", "bank"),
    "ATM": ("amenity", "atm"), "超市": ("shop", "supermarket"),
    "便利店": ("shop", "convenience"), "商场": ("shop", "mall"),
    "地铁站": ("railway", "station"), "公交站": ("highway", "bus_stop"),
    "机场": ("aeroway", "aerodrome"), "学校": ("amenity", "school"),
    "公园": ("leisure", "park"), "电影院": ("amenity", "cinema"),
    "健身房": ("leisure", "fitness_centre"), "理发": ("shop", "hairdresser"),
    "厕所": ("amenity", "toilets"), "邮局": ("amenity", "post_office"),
    "加油": ("amenity", "fuel"), "充电": ("amenity", "charging_station"),
}


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def http_json(url, data=None, timeout=TIMEOUT, retries=2):
    headers = {"User-Agent": UA}
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers, data=body)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="ignore"))
        except Exception as e:
            last = e
            time.sleep(0.8)
    raise last


def geocode(query, limit=5):
    q = urllib.parse.urlencode({"q": query, "format": "jsonv2",
                                "limit": limit, "addressdetails": 1,
                                "accept-language": "zh"})
    rows = http_json(f"{NOMINATIM}/search?{q}")
    return [{"name": r.get("display_name"), "lat": float(r["lat"]),
             "lon": float(r["lon"]), "category": r.get("category"),
             "type": r.get("type"), "importance": r.get("importance"),
             "address": r.get("address")} for r in rows]


def resolve_point(text):
    """地名或 'lat,lon' -> (lat, lon, label)。"""
    s = str(text).strip()
    if "," in s:
        a, b = s.split(",", 1)
        try:
            return float(a), float(b), s
        except ValueError:
            pass
    hits = geocode(s, limit=1)
    if not hits:
        fail(f"找不到地点: {text}", code="NOT_FOUND")
    return hits[0]["lat"], hits[0]["lon"], hits[0]["name"]


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def cmd_geocode(args):
    rows = geocode(args.place, limit=args.limit)
    emit({"query": args.place, "results": rows}, args,
         cols=["name", "lat", "lon", "type"])


def cmd_reverse(args):
    try:
        lat_s, lon_s = args.coord.split(",", 1)
        lat, lon = float(lat_s), float(lon_s)
    except ValueError:
        fail(f"坐标格式应为 'lat,lon': {args.coord}", code="INVALID")
    q = urllib.parse.urlencode({"lat": lat, "lon": lon, "format": "jsonv2",
                                "accept-language": "zh"})
    data = http_json(f"{NOMINATIM}/reverse?{q}")
    if not data.get("display_name"):
        fail("该坐标无地址结果", code="NOT_FOUND")
    emit({"lat": lat, "lon": lon, "name": data.get("display_name"),
          "category": data.get("category"), "type": data.get("type"),
          "address": data.get("address")}, args)


def cmd_route(args):
    lat1, lon1, label1 = resolve_point(args.origin)
    lat2, lon2, label2 = resolve_point(args.dest)
    profile = OSRM_PROFILES[args.mode]
    url = (f"https://routing.openstreetmap.de/{profile}/route/v1/driving/"
           f"{lon1},{lat1};{lon2},{lat2}?overview=false&steps=true")
    data = http_json(url)
    routes = data.get("routes") or []
    if not routes:
        fail("无路线结果", code="NOT_FOUND")
    r = routes[0]
    steps = []
    for leg in r.get("legs", []):
        for st in leg.get("steps", []):
            man = st.get("maneuver", {})
            steps.append({"instruction": man.get("type"),
                          "modifier": man.get("modifier"),
                          "road": st.get("name"),
                          "distance_m": round(st.get("distance", 0))})
    emit({"from": label1, "to": label2, "mode": args.mode,
          "distance_km": round(r["distance"] / 1000, 2),
          "duration_min": round(r["duration"] / 60, 1),
          "straight_km": round(haversine_m(lat1, lon1, lat2, lon2) / 1000, 2),
          "steps": steps if args.steps else steps[:0] or None,
          "steps_count": len(steps)}, args)


def overpass_query(ql):
    # 公共 Overpass 集群负载波动大：同一查询时而 3 秒返回、时而 504，
    # 多镜像 × 多轮重试是实测最有效的策略（仍失败则如实报 UPSTREAM）
    last = None
    for rnd in range(3):
        for url in OVERPASS_MIRRORS:
            try:
                return http_json(url, data={"data": ql}, timeout=35,
                                 retries=1)
            except Exception as e:
                last = e
        if rnd < 2:
            time.sleep(2)
    raise last


def cmd_poi(args):
    if args.category not in POI_TYPES:
        fail(f"不支持的类别: {args.category}（支持：{', '.join(POI_TYPES)}）",
             code="INVALID")
    key, val = POI_TYPES[args.category]
    lat, lon, label = resolve_point(args.near)
    # 只查 node（绝大多数 POI 是点要素）；way 面要素会让 Overpass 慢数倍，
    # 实测同一查询 node-only 4.8s vs 含 way 超时（取舍已在 README 注明）
    ql = (f'[out:json][timeout:20];'
          f'node["{key}"="{val}"](around:{args.radius},{lat},{lon});'
          f'out {args.limit * 3};')
    data = overpass_query(ql)
    items = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:zh")
        if not name:
            continue
        elat = el.get("lat") or (el.get("center") or {}).get("lat")
        elon = el.get("lon") or (el.get("center") or {}).get("lon")
        if elat is None:
            continue
        items.append({"name": name, "lat": elat, "lon": elon,
                      "distance_m": round(haversine_m(lat, lon, elat, elon)),
                      "address": tags.get("addr:full") or tags.get("addr:street"),
                      "opening_hours": tags.get("opening_hours"),
                      "phone": tags.get("phone") or tags.get("contact:phone")})
    items.sort(key=lambda x: x["distance_m"])
    emit({"category": args.category, "near": label,
          "center": {"lat": lat, "lon": lon}, "radius_m": args.radius,
          "count": len(items), "results": items[:args.limit]}, args,
         cols=["name", "distance_m", "address"])


def cmd_doctor(args):
    checks = []
    for name, fn in (("nominatim", lambda: geocode("上海外滩", 1)),
                     ("osrm", lambda: http_json(
                         "https://routing.openstreetmap.de/routed-car/route/"
                         "v1/driving/116.397,39.907;116.407,39.917?overview=false")),
                     ("overpass", lambda: overpass_query(
                         '[out:json][timeout:20];'
                         'node["amenity"="cafe"](around:300,39.907,116.397);'
                         'out 1;'))):
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
    {"name": "geocode", "usage": "map geocode <地名> [--limit N]",
     "desc": "地名 -> 经纬度与地址结构（支持中文）"},
    {"name": "reverse", "usage": "map reverse <lat,lon>",
     "desc": "经纬度 -> 地址"},
    {"name": "route", "usage": "map route <起点> <终点> [--mode driving|walking|cycling] [--steps]",
     "desc": "路线规划：距离、时长（可选分步导航）"},
    {"name": "poi", "usage": "map poi <类别> <地点> [--radius 米] [--limit N]",
     "desc": "周边 POI 按距离排序（餐厅/咖啡/酒店/医院/药店/加油站/停车场/地铁站等 30 类）"},
    {"name": "doctor", "usage": "map doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "map commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "地点可用中文名或 'lat,lon'；错误带 code"}, args)


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
    p = argparse.ArgumentParser(prog="map", description="地图出行 CLI（OpenStreetMap 生态，免密钥）")
    p.add_argument("--version", action="version", version=f"map {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("geocode", help="地名 -> 经纬度")
    sp.add_argument("place")
    sp.add_argument("--limit", type=int, default=5)
    sp.set_defaults(func=cmd_geocode)

    sp = sub.add_parser("reverse", help="经纬度 -> 地址")
    sp.add_argument("coord", help="'lat,lon'")
    sp.set_defaults(func=cmd_reverse)

    sp = sub.add_parser("route", help="路线规划")
    sp.add_argument("origin")
    sp.add_argument("dest")
    sp.add_argument("--mode", default="driving",
                    choices=["driving", "walking", "cycling"])
    sp.add_argument("--steps", action="store_true")
    sp.set_defaults(func=cmd_route)

    sp = sub.add_parser("poi", help="周边 POI")
    sp.add_argument("category", help="如 餐厅/咖啡/酒店/医院/药店/加油站/停车场/地铁站")
    sp.add_argument("near", help="中心地点名或 'lat,lon'")
    sp.add_argument("--radius", type=int, default=1000)
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_poi)

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
