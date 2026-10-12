#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hot — 全网热搜聚合 CLI（供 AI agent / 脚本调用）

数据源（均为公开接口，无需密钥）：
  * 知乎热榜  api.zhihu.com/topstory/hot-lists/total
  * 百度热搜  top.baidu.com/api/board（实时榜）
  * 头条热榜  toutiao.com/hot-event/hot-board
  * B站热门   api.bilibili.com/x/web-interface/popular（热门视频；
              官方热搜词接口已下线 404，不提供）
  * 微博热搜  weibo.com/ajax/side/hotSearch（需访客 cookie，本工具自动
              走 passport 访客流程获取并缓存；失败时该源单独报错不拖垮其他源）

默认 JSON 输出；全局 --table/--compact/--fields。错误带 code，退出码 1。
仅使用 Python 标准库。
"""
import argparse
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
TIMEOUT = 25
VERSION = "1.1.0"
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".hot_cache")
WEIBO_AUTH_FILE = os.path.join(os.path.expanduser("~"), ".weibo_auth.json")
WEIBO_FLOW_FILE = os.path.join(CACHE_DIR, "weibo_login_flow.json")
PASSPORT_JAR_FILE = os.path.join(CACHE_DIR, "passport_cookies.txt")


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def http_text(url, opener=None, headers=None, timeout=TIMEOUT):
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    open_fn = opener.open if opener else urllib.request.urlopen
    last = None
    for attempt in range(2):
        try:
            with open_fn(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            last = e
            time.sleep(0.8)
    raise last


def http_json(url, **kw):
    return json.loads(http_text(url, **kw))


# ---------------------------------------------------------------- sources

def src_zhihu(limit):
    data = http_json("https://api.zhihu.com/topstory/hot-lists/total?limit=50")
    items = []
    for i, it in enumerate(data.get("data", [])[:limit], 1):
        t = it.get("target", {})
        qid = t.get("id")
        items.append({"rank": i, "title": t.get("title"),
                      "heat": it.get("detail_text"),
                      "url": f"https://www.zhihu.com/question/{qid}"
                             if qid else t.get("url")})
    return items


def src_baidu(limit):
    data = http_json("https://top.baidu.com/api/board?platform=wise&tab=realtime")
    cards = (data.get("data") or {}).get("cards") or []
    raw = []
    if cards:
        for c in cards[0].get("content", []):
            raw.extend(c.get("content", []))
    items = []
    for i, it in enumerate(raw[:limit], 1):
        items.append({"rank": i, "title": it.get("word"),
                      "heat": it.get("hotScore") or it.get("desc"),
                      "url": it.get("url") or it.get("rawUrl")})
    return items


def src_toutiao(limit):
    data = http_json("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
    items = []
    for i, it in enumerate((data.get("data") or [])[:limit], 1):
        items.append({"rank": i, "title": it.get("Title"),
                      "heat": it.get("HotValue"),
                      "label": it.get("Label") or None,
                      "url": it.get("Url")})
    return items


def src_bili(limit):
    data = http_json(f"https://api.bilibili.com/x/web-interface/popular?ps={min(limit, 50)}&pn=1")
    items = []
    for i, v in enumerate((data.get("data") or {}).get("list", [])[:limit], 1):
        st = v.get("stat", {})
        items.append({"rank": i, "title": v.get("title"),
                      "author": (v.get("owner") or {}).get("name"),
                      "heat": st.get("view"),
                      "url": f"https://www.bilibili.com/video/{v.get('bvid')}"})
    return items


def _weibo_opener():
    os.makedirs(CACHE_DIR, exist_ok=True)
    jar = http.cookiejar.MozillaCookieJar(
        os.path.join(CACHE_DIR, "weibo_cookies.txt"))
    if os.path.exists(jar.filename):
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar)), jar


def _weibo_visitor(opener, jar):
    fp = urllib.parse.quote('{"os":"1","browser":"Chrome"}')
    t = http_text("https://passport.weibo.com/visitor/genvisitor"
                  f"?cb=gen_callback&fp={fp}", opener=opener)
    m = re.search(r'"tid":"([^"]+)"', t)
    if not m:
        raise RuntimeError("访客 tid 获取失败")
    http_text("https://passport.weibo.com/visitor/visitor?a=incarnate"
              f"&t={urllib.parse.quote(m.group(1))}&w=2&c=095&gc="
              "&cb=cross_domain&from=weibo&_rand=0.42", opener=opener)
    jar.save(ignore_discard=True, ignore_expires=True)


def _shape_weibo(band, limit):
    items = []
    for i, b in enumerate(band[:limit], 1):
        items.append({
            "rank": i, "title": b.get("word"),
            "heat": b.get("num"),
            "label": b.get("label_name") or None,
            "url": "https://s.weibo.com/weibo?q="
                   + urllib.parse.quote("#" + (b.get("word") or "") + "#")})
    return items


# ---------------------------------------------------------------- weibo login

def _passport_opener():
    os.makedirs(CACHE_DIR, exist_ok=True)
    jar = http.cookiejar.MozillaCookieJar(PASSPORT_JAR_FILE)
    if os.path.exists(PASSPORT_JAR_FILE):
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar)), jar


def load_weibo_auth():
    if not os.path.exists(WEIBO_AUTH_FILE):
        return None
    try:
        with open(WEIBO_AUTH_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _auth_weibo_opener():
    """带已保存登录 cookie 的 opener（登录态优先于访客流程）。"""
    auth = load_weibo_auth()
    if not auth:
        return None
    opener, jar = _weibo_opener()
    for name, val in (auth.get("cookies") or {}).items():
        jar.set_cookie(http.cookiejar.Cookie(
            0, name, val, None, False, ".weibo.com", True, False,
            "/", True, False, None, False, None, None, {}))
    return opener


def cmd_login_qr(args):
    opener, jar = _passport_opener()
    http_text("https://passport.weibo.com/", opener=opener)  # 预热 passport 域
    data = json.loads(http_text(
        "https://passport.weibo.com/sso/v2/qrcode/image?entry=miniblog&size=180",
        opener=opener, headers={"Referer": "https://weibo.com/"}))
    if data.get("retcode") != 20000000:
        fail(f"二维码生成失败: {data.get('msg')}", code="UPSTREAM")
    d = data["data"]
    with open(WEIBO_FLOW_FILE, "w", encoding="utf-8") as f:
        json.dump({"qrid": d["qrid"], "created": int(time.time())}, f)
    try:
        jar.save(ignore_discard=True, ignore_expires=True)
    except Exception:
        pass
    # 官方二维码图直接下载展示（保证可扫）；链接同时给出
    png = os.path.join(CACHE_DIR, "weibo_login_qr.png")
    img_url = d["image"].replace("\\/", "/")
    req = urllib.request.Request(img_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        with open(png, "wb") as f:
            f.write(resp.read())
    emit({"action": "scan_required", "qrid": d["qrid"], "qr_png": png,
          "hint": "用微博 App 扫码并确认；随后运行 hot login poll"}, args)


def cmd_login_poll(args):
    if not os.path.exists(WEIBO_FLOW_FILE):
        fail("无进行中的登录流程：先运行 hot login qr", code="INVALID")
    flow = json.load(open(WEIBO_FLOW_FILE, encoding="utf-8"))
    opener, jar = _passport_opener()
    data = json.loads(http_text(
        "https://passport.weibo.com/sso/v2/qrcode/check?entry=miniblog&qrid="
        + urllib.parse.quote(flow["qrid"]), opener=opener,
        headers={"Referer": "https://weibo.com/"}))
    try:
        jar.save(ignore_discard=True, ignore_expires=True)
    except Exception:
        pass
    rc = data.get("retcode")
    if rc == 50114001:
        emit({"logged_in": False, "status": "waiting_scan"}, args)
        return
    if rc == 50114002:
        emit({"logged_in": False, "status": "scanned_unconfirmed"}, args)
        return
    if rc == 50114004:
        emit({"logged_in": False, "status": "already_consumed",
              "note": "该二维码已完成确认但凭据未落盘，请重新 hot login qr 扫码"},
             args)
        return
    if rc != 20000000:
        fail(f"登录轮询失败 retcode={rc}（二维码可能已过期，重新 hot login qr）",
             code="UPSTREAM")
    # 已扫码确认。先保存原始响应与当前 cookie（校准依据），再容错地走完
    # 换取登录态的后续跳转；任一步断开都不丢已拿到的东西。
    with open(os.path.join(CACHE_DIR, "weibo_check_success.json"), "w",
              encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    d = data.get("data") or {}
    # check 成功响应直接给出一次性登录 URL（data.url，含 alt 单次令牌）：
    # 必须原样、只调用一次——实测任何猜测的变体调用都会把 alt 作废
    follow = []
    if isinstance(d, dict) and d.get("url"):
        follow.append(d["url"])
    follow.append("https://weibo.com/")
    for u in follow:
        try:
            http_text(u, opener=opener, headers={"Referer": "https://weibo.com/"})
        except Exception:
            pass
        try:
            jar.save(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
    cookies = {}
    for c in jar:
        if "weibo.com" in c.domain or "sina.com.cn" in c.domain:
            cookies[c.name] = c.value
    if "SUB" not in cookies:
        emit({"logged_in": False, "status": "cookies_incomplete",
              "got": sorted(cookies),
              "check_data_keys": sorted(d) if isinstance(d, dict) else str(d),
              "note": "已确认扫码但未拿到 SUB cookie，原始响应已存 "
                      "~/.hot_cache/weibo_check_success.json 供校准"},
             args)
        return
    auth = {"cookies": cookies,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(WEIBO_AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(auth, f, ensure_ascii=False)
    os.chmod(WEIBO_AUTH_FILE, 0o600)
    try:
        os.remove(WEIBO_FLOW_FILE)
    except OSError:
        pass
    emit({"logged_in": True, "saved_at": auth["saved_at"],
          "cookies": sorted(cookies)}, args)


def cmd_login_status(args):
    auth = load_weibo_auth()
    if not auth:
        emit({"logged_in": False}, args)
        return
    opener = _auth_weibo_opener()
    ok = False
    try:
        data = json.loads(http_text(
            "https://weibo.com/ajax/side/hotSearch", opener=opener,
            headers={"Referer": "https://weibo.com/"}, timeout=30))
        ok = bool((data.get("data") or {}).get("realtime"))
    except Exception:
        ok = False
    emit({"logged_in": ok, "saved_at": auth.get("saved_at"),
          "note": None if ok else "凭据可能已失效，请重新 hot login qr"}, args)


def cmd_login_logout(args):
    if os.path.exists(WEIBO_AUTH_FILE):
        os.remove(WEIBO_AUTH_FILE)
    emit({"logged_out": True}, args)


def src_weibo(limit):
    # 登录态优先（更稳），失败再落访客流程
    auth_opener = _auth_weibo_opener()
    if auth_opener is not None:
        try:
            data = json.loads(http_text(
                "https://weibo.com/ajax/side/hotSearch", opener=auth_opener,
                headers={"Referer": "https://weibo.com/"}, timeout=30))
            band = (data.get("data") or {}).get("realtime") or []
            if band:
                return _shape_weibo(band, limit)
        except Exception:
            pass
    opener, jar = _weibo_opener()
    for attempt in range(2):
        try:
            data = json.loads(http_text(
                "https://weibo.com/ajax/side/hotSearch", opener=opener,
                headers={"Referer": "https://weibo.com/"}, timeout=30))
            band = (data.get("data") or {}).get("realtime") or []
            if band:
                return _shape_weibo(band, limit)
        except Exception:
            pass
        if attempt == 0:
            _weibo_visitor(opener, jar)
    raise RuntimeError("微博热搜获取失败（访客流程后仍不可用）")


SOURCES = {"zhihu": ("知乎热榜", src_zhihu),
           "baidu": ("百度热搜", src_baidu),
           "toutiao": ("头条热榜", src_toutiao),
           "bili": ("B站热门视频", src_bili),
           "weibo": ("微博热搜", src_weibo)}


def cmd_list(args):
    if args.source == "all":
        out = {}
        for key, (label, fn) in SOURCES.items():
            try:
                out[key] = {"label": label, "ok": True,
                            "items": fn(args.limit)}
            except Exception as e:
                out[key] = {"label": label, "ok": False,
                            "error": str(e)[:160], "items": []}
        emit({"sources": out}, args)
    else:
        label, fn = SOURCES[args.source]
        try:
            items = fn(args.limit)
        except Exception as e:
            fail(f"{label} 获取失败: {e}", code="UPSTREAM")
        emit({"source": args.source, "label": label, "items": items}, args,
             cols=["rank", "title", "heat"])


def cmd_doctor(args):
    checks = []
    for key, (label, fn) in SOURCES.items():
        t0 = time.time()
        try:
            n = len(fn(3))
            checks.append({"name": key, "label": label, "ok": n > 0,
                           "ms": int((time.time() - t0) * 1000),
                           "items": n})
        except Exception as e:
            checks.append({"name": key, "label": label, "ok": False,
                           "ms": int((time.time() - t0) * 1000),
                           "detail": str(e)[:120]})
    ok = any(c["ok"] for c in checks)
    emit({"ok": ok, "note": "聚合源：个别源失败不影响其他源（weibo 依赖访客流程，最不稳定）",
          "checks": checks}, args)
    if not ok:
        sys.exit(1)


COMMANDS_MANIFEST = [
    {"name": "list", "usage": "hot list [--source all|zhihu|baidu|toutiao|"
     "bili|weibo] [--limit N]",
     "desc": "热搜聚合：all 返回全部源（单源失败隔离），或指定单个源"},
    {"name": "login qr", "usage": "hot login qr",
     "desc": "微博扫码登录：生成官方二维码图（存 ~/.hot_cache/）"},
    {"name": "login poll", "usage": "hot login poll",
     "desc": "轮询扫码状态；成功后凭据存 ~/.weibo_auth.json（0600），微博源优先用登录态"},
    {"name": "login status", "usage": "hot login status", "desc": "微博登录状态"},
    {"name": "login logout", "usage": "hot login logout", "desc": "退出微博登录"},
    {"name": "doctor", "usage": "hot doctor", "desc": "逐源健康检查"},
    {"name": "commands", "usage": "hot commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "热度字段口径各源不同（知乎为热度文本、百度为指数、"
                         "微博为搜索量），跨源不可直接比较；错误带 code"}, args)


# ---------------------------------------------------------------- output

_LIST_KEYS = ("items", "checks")


def _pick_fields(obj, fields):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "sources" and isinstance(v, dict):
                out[k] = {sk: {"label": sv.get("label"), "ok": sv.get("ok"),
                               "items": [{kk: vv for kk, vv in r.items()
                                          if kk in fields}
                                         for r in sv.get("items", [])]}
                          for sk, sv in v.items()}
            elif k in _LIST_KEYS and isinstance(v, list):
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
    p = argparse.ArgumentParser(prog="hot", description="全网热搜聚合 CLI（公开接口，免密钥）")
    p.add_argument("--version", action="version", version=f"hot {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list", help="热搜列表（默认全部源聚合）")
    sp.add_argument("--source", default="all",
                    choices=["all"] + list(SOURCES))
    sp.add_argument("--limit", type=int, default=30)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("login", help="微博扫码登录（子命令 qr/poll/status/logout）")
    sp.add_argument("action", choices=["qr", "poll", "status", "logout"])
    sp.set_defaults(func=lambda a: {"qr": cmd_login_qr, "poll": cmd_login_poll,
                                    "status": cmd_login_status,
                                    "logout": cmd_login_logout}[a.action](a))

    sp = sub.add_parser("doctor", help="逐源健康检查")
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
