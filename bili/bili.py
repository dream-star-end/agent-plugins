#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bili — 哔哩哔哩查询 CLI（供 AI agent / 脚本调用）

数据源：B站公开 Web 接口（无需登录）：
  * 搜索   x/web-interface/wbi/search/all/v2（WBI 签名，本工具自动完成）
  * 视频   www.bilibili.com/video 页 __INITIAL_STATE__ 解析
           （view 接口对机房 IP 常 412，页面解析更稳；view 作为兜底）
  * 排行   x/web-interface/ranking/v2；热门 x/web-interface/popular
  * UP主   x/web-interface/card；评论 x/v2/reply（buvid 指纹自动获取）

默认 JSON 输出；全局 --table/--compact/--fields。错误带 code，退出码 1。
仅使用 Python 标准库。
"""
import argparse
import gzip
import hashlib
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/126 Safari/537.36")
TIMEOUT = 25
VERSION = "1.3.0"
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".bili_cache")
AUTH_FILE = os.path.join(os.path.expanduser("~"), ".bili_auth.json")
FLOW_FILE = os.path.join(CACHE_DIR, "login_flow.json")
AUTH_COOKIE_NAMES = ("SESSDATA", "bili_jct", "DedeUserID",
                     "DedeUserID__ckMd5", "sid")
MIXIN_TABLE = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
               27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
               37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
               22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52]

_opener = None


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def opener():
    global _opener
    if _opener is None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        jar = http.cookiejar.MozillaCookieJar(
            os.path.join(CACHE_DIR, "cookies.txt"))
        if os.path.exists(jar.filename):
            try:
                jar.load(ignore_discard=True, ignore_expires=True)
            except Exception:
                pass
        _opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        _opener._jar = jar
    return _opener


def http_bytes(url, headers=None):
    h = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    last = None
    for attempt in range(3):
        try:
            with opener().open(req, timeout=TIMEOUT) as resp:
                b = resp.read()
            if b[:2] == b"\x1f\x8b":
                b = gzip.decompress(b)
            return b
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (502, 503, 504):
                raise
        except Exception as e:
            last = e
        if attempt < 2:
            time.sleep(0.7 * (attempt + 1))
    raise last


def http_json(url, headers=None):
    return json.loads(http_bytes(url, headers).decode("utf-8", "ignore"))


def http_post_json(url, form, headers=None):
    """表单 POST（写操作专用：单次尝试不重试，防止重复提交）。"""
    h = {"User-Agent": UA, "Referer": "https://www.bilibili.com/",
         "Content-Type": "application/x-www-form-urlencoded"}
    h.update(headers or {})
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(url, data=body, headers=h)
    with opener().open(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def ensure_buvid():
    jar = opener()._jar
    if any(c.name == "buvid3" for c in jar):
        return
    data = http_json("https://api.bilibili.com/x/frontend/finger/spi")
    d = data.get("data") or {}
    for name, val in (("buvid3", d.get("b_3")), ("buvid4", d.get("b_4"))):
        if val:
            jar.set_cookie(http.cookiejar.Cookie(
                0, name, val, None, False, ".bilibili.com", True, False,
                "/", True, False, None, False, None, None, {}))
    try:
        jar.save(ignore_discard=True, ignore_expires=True)
    except Exception:
        pass


# ---------------------------------------------------------------- auth / login

def _set_cookie(jar, name, value):
    jar.set_cookie(http.cookiejar.Cookie(
        0, name, value, None, False, ".bilibili.com", True, False,
        "/", True, False, None, False, None, None, {}))


def load_auth():
    if not os.path.exists(AUTH_FILE):
        return None
    try:
        with open(AUTH_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def apply_auth():
    """把已保存的登录凭据注入 cookie jar；返回 auth dict 或 None。"""
    auth = load_auth()
    if not auth:
        return None
    jar = opener()._jar
    for name, val in (auth.get("cookies") or {}).items():
        _set_cookie(jar, name, val)
    return auth


def require_auth():
    auth = apply_auth()
    if not auth:
        fail("未登录：先运行 bili login qr 扫码登录", code="AUTH")
    return auth


def fetch_nav():
    data = http_json("https://api.bilibili.com/x/web-interface/nav")
    return data.get("data") or {}


def _qr_png(url, path):
    """用内置 qrcodegen（MIT，单文件）把登录 URL 渲染为 PNG（stdlib 写图）。"""
    import struct
    import zlib
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from qrcodegen import QrCode
    qr = QrCode.encode_text(url, QrCode.Ecc.MEDIUM)
    size, scale, border = qr.get_size(), 10, 4
    px = (size + border * 2) * scale
    raw = bytearray()
    for y in range(px):
        raw.append(0)
        my = y // scale - border
        for x in range(px):
            mx = x // scale - border
            dark = 0 <= mx < size and 0 <= my < size and qr.get_module(mx, my)
            raw.append(0 if dark else 255)

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", px, px, 8, 0, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return path


def cmd_login_qr(args):
    ensure_buvid()
    data = http_json("https://passport.bilibili.com/x/passport-login/web/"
                     "qrcode/generate")
    if data.get("code") != 0:
        fail(f"二维码生成失败: {data.get('message')}", code="UPSTREAM")
    d = data["data"]
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(FLOW_FILE, "w", encoding="utf-8") as f:
        json.dump({"qrcode_key": d["qrcode_key"], "created": int(time.time())},
                  f)
    png = os.path.join(CACHE_DIR, "login_qr.png")
    _qr_png(d["url"], png)
    emit({"action": "scan_required", "qrcode_key": d["qrcode_key"],
          "qr_png": png, "expires_in_sec": 180,
          "hint": "用 B站 App 扫码并确认；随后运行 bili login poll"}, args)


def cmd_login_poll(args):
    if not os.path.exists(FLOW_FILE):
        fail("无进行中的登录流程：先运行 bili login qr", code="INVALID")
    flow = json.load(open(FLOW_FILE, encoding="utf-8"))
    url = ("https://passport.bilibili.com/x/passport-login/web/qrcode/poll?"
           + urllib.parse.urlencode({"qrcode_key": flow["qrcode_key"]}))
    data = http_json(url)
    d = data.get("data") or {}
    code = d.get("code")
    if code == 86101:
        emit({"logged_in": False, "status": "waiting_scan",
              "message": d.get("message")}, args)
        return
    if code == 86090:
        emit({"logged_in": False, "status": "scanned_unconfirmed",
              "message": d.get("message")}, args)
        return
    if code == 86038:
        fail("二维码已过期：重新运行 bili login qr", code="EXPIRED")
    if code != 0:
        fail(f"登录轮询失败: {d.get('message')}", code="UPSTREAM")
    # 成功：优先从回调 URL 解析 cookie，其次从 jar 提取
    cookies = {}
    cb = urllib.parse.urlparse(d.get("url", ""))
    for k, v in urllib.parse.parse_qsl(cb.query):
        if k in AUTH_COOKIE_NAMES:
            cookies[k] = v
    jar = opener()._jar
    for c in jar:
        if c.name in AUTH_COOKIE_NAMES and c.name not in cookies:
            cookies[c.name] = c.value
    if "SESSDATA" not in cookies:
        fail("登录成功但未拿到 SESSDATA cookie", code="UPSTREAM")
    for k, v in cookies.items():
        _set_cookie(jar, k, v)
    nav = fetch_nav()
    auth = {"cookies": cookies, "mid": nav.get("mid"),
            "uname": nav.get("uname"),
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(auth, f, ensure_ascii=False)
    os.chmod(AUTH_FILE, 0o600)
    try:
        os.remove(FLOW_FILE)
    except OSError:
        pass
    emit({"logged_in": True, "mid": nav.get("mid"),
          "uname": nav.get("uname"),
          "vip": (nav.get("vipStatus") == 1),
          "level": (nav.get("level_info") or {}).get("current_level")}, args)


def cmd_login_status(args):
    auth = apply_auth()
    if not auth:
        emit({"logged_in": False}, args)
        return
    nav = fetch_nav()
    if not nav.get("isLogin"):
        emit({"logged_in": False, "note": "凭据已失效，请重新 bili login qr",
              "saved_at": auth.get("saved_at")}, args)
        return
    emit({"logged_in": True, "mid": nav.get("mid"), "uname": nav.get("uname"),
          "level": (nav.get("level_info") or {}).get("current_level"),
          "vip": nav.get("vipStatus") == 1, "coins": nav.get("money"),
          "saved_at": auth.get("saved_at")}, args)


def cmd_login_logout(args):
    if os.path.exists(AUTH_FILE):
        os.remove(AUTH_FILE)
    jar = opener()._jar
    for c in list(jar):
        if c.name in AUTH_COOKIE_NAMES:
            jar.clear(c.domain, c.path, c.name)
    try:
        jar.save(ignore_discard=True, ignore_expires=True)
    except Exception:
        pass
    emit({"logged_out": True}, args)


# ---------------------------------------------------------------- WBI

def wbi_keys():
    path = os.path.join(CACHE_DIR, "wbi.json")
    today = time.strftime("%Y-%m-%d")
    if os.path.exists(path):
        try:
            saved = json.load(open(path, encoding="utf-8"))
            if saved.get("date") == today:
                return saved["img"], saved["sub"]
        except Exception:
            pass
    data = http_json("https://api.bilibili.com/x/web-interface/nav")
    wbi = (data.get("data") or {}).get("wbi_img") or {}
    img = wbi.get("img_url", "").rsplit("/", 1)[-1].split(".")[0]
    sub = wbi.get("sub_url", "").rsplit("/", 1)[-1].split(".")[0]
    if not img or not sub:
        raise RuntimeError("WBI 密钥获取失败")
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump({"date": today, "img": img, "sub": sub},
              open(path, "w", encoding="utf-8"))
    return img, sub


def wbi_sign(params):
    img, sub = wbi_keys()
    raw = img + sub
    mixin = "".join(raw[i] for i in MIXIN_TABLE)[:32]
    p = dict(params)
    p["wts"] = int(time.time())
    items = []
    for k in sorted(p):
        v = re.sub(r"[!'()*]", "", str(p[k]))
        items.append((k, v))
    query = urllib.parse.urlencode(items)
    p["w_rid"] = hashlib.md5((query + mixin).encode()).hexdigest()
    return p


# ---------------------------------------------------------------- video data

def fetch_video_data(ref):
    """BV 号/av 号/完整链接 -> videoData（页面解析为主，view 接口兜底）。"""
    ref = str(ref).strip()
    m = re.search(r"(BV[0-9A-Za-z]{10})", ref)
    avm = re.search(r"av(\d+)", ref)
    if m:
        bvid = m.group(1)
        query = f"bvid={bvid}"
        page_url = f"https://www.bilibili.com/video/{bvid}"
    elif avm or ref.isdigit():
        aid = avm.group(1) if avm else ref
        query = f"aid={aid}"
        page_url = f"https://www.bilibili.com/video/av{aid}"
    else:
        fail(f"无法识别的视频引用: {ref}（需 BV 号/av 号/链接）", code="INVALID")
    # 页面解析（view 接口对不少 IP 段 412，页面更稳）
    try:
        html = http_bytes(page_url).decode("utf-8", "ignore")
        mm = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\(", html, re.S)
        if mm:
            vd = json.loads(mm.group(1)).get("videoData")
            # 个别稿件页面只给残缺 videoData（仅 owner/stat，如已下架稿件），
            # 必须含 aid 才算完整，否则落到 view 接口兜底
            if vd and vd.get("aid"):
                return vd
    except Exception:
        pass
    ensure_buvid()
    data = http_json(f"https://api.bilibili.com/x/web-interface/view?{query}")
    if data.get("code") != 0:
        fail(f"视频获取失败: {data.get('message')}", code="UPSTREAM")
    return data["data"]


def shape_video(vd):
    st = vd.get("stat") or {}
    return {"bvid": vd.get("bvid"), "aid": vd.get("aid"),
            "title": vd.get("title"),
            "author": (vd.get("owner") or {}).get("name"),
            "author_mid": (vd.get("owner") or {}).get("mid"),
            "pic": vd.get("pic"),
            "desc": (vd.get("desc") or "")[:500],
            "duration_sec": vd.get("duration"),
            "pubdate": time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(vd["pubdate"]))
            if vd.get("pubdate") else None,
            "category": vd.get("tname"),
            "stats": {"view": st.get("view"), "danmaku": st.get("danmaku"),
                      "reply": st.get("reply"), "favorite": st.get("favorite"),
                      "coin": st.get("coin"), "share": st.get("share"),
                      "like": st.get("like")},
            "pages": [{"cid": p.get("cid"), "part": p.get("part"),
                       "duration_sec": p.get("duration")}
                      for p in vd.get("pages", [])],
            "url": f"https://www.bilibili.com/video/{vd.get('bvid')}"}


def cmd_video(args):
    emit(shape_video(fetch_video_data(args.ref)), args)


def cmd_search(args):
    ensure_buvid()
    params = wbi_sign({"keyword": args.keyword, "page": 1,
                       "search_type": "video", "order": args.order})
    url = ("https://api.bilibili.com/x/web-interface/wbi/search/all/v2?"
           + urllib.parse.urlencode(params))
    data = http_json(url)
    if data.get("code") != 0:
        fail(f"搜索失败: {data.get('message')}", code="UPSTREAM")
    groups = (data.get("data") or {}).get("result") or []
    videos = []
    for g in groups:
        if g.get("result_type") == "video":
            videos = g.get("data") or []
    items = []
    for v in videos[:args.limit]:
        items.append({
            "bvid": v.get("bvid"),
            "title": re.sub(r"</?em[^>]*>", "", v.get("title") or ""),
            "author": v.get("author"), "mid": v.get("mid"),
            "play": v.get("play"), "danmaku": v.get("video_review"),
            "duration": v.get("duration"),
            "pubdate": time.strftime("%Y-%m-%d", time.localtime(v["pubdate"]))
            if v.get("pubdate") else None,
            "desc": (v.get("description") or "")[:200],
            "url": f"https://www.bilibili.com/video/{v.get('bvid')}"})
    emit({"keyword": args.keyword, "count": len(items), "results": items},
         args, cols=["bvid", "title", "author", "play"])


def _list_shape(v):
    st = v.get("stat") or {}
    return {"bvid": v.get("bvid"), "title": v.get("title"),
            "author": (v.get("owner") or {}).get("name"),
            "play": st.get("view"), "danmaku": st.get("danmaku"),
            "duration_sec": v.get("duration"),
            "url": f"https://www.bilibili.com/video/{v.get('bvid')}"}


def cmd_rank(args):
    data = http_json("https://api.bilibili.com/x/web-interface/ranking/v2"
                     f"?rid={args.rid}&type=all")
    if data.get("code") != 0:
        fail(f"排行榜获取失败: {data.get('message')}", code="UPSTREAM")
    items = [_list_shape(v) for v in
             (data.get("data") or {}).get("list", [])[:args.limit]]
    for i, it in enumerate(items, 1):
        it["rank"] = i
    emit({"rid": args.rid, "results": items}, args,
         cols=["rank", "title", "author", "play"])


def cmd_popular(args):
    data = http_json("https://api.bilibili.com/x/web-interface/popular"
                     f"?ps={min(args.limit, 50)}&pn=1")
    if data.get("code") != 0:
        fail(f"热门获取失败: {data.get('message')}", code="UPSTREAM")
    items = [_list_shape(v) for v in
             (data.get("data") or {}).get("list", [])[:args.limit]]
    for i, it in enumerate(items, 1):
        it["rank"] = i
    emit({"results": items}, args, cols=["rank", "title", "author", "play"])


def cmd_up(args):
    data = http_json("https://api.bilibili.com/x/web-interface/card"
                     f"?mid={args.mid}")
    if data.get("code") != 0:
        fail(f"UP主获取失败: {data.get('message')}", code="UPSTREAM")
    d = data.get("data") or {}
    card = d.get("card") or {}
    emit({"mid": args.mid, "name": card.get("name"),
          "sign": card.get("sign"), "level": card.get("level_info", {}).get(
              "current_level") if isinstance(card.get("level_info"), dict)
          else None,
          "fans": d.get("follower"), "following": card.get("attention"),
          "likes": d.get("like_num"),
          "archive_count": d.get("archive_count"),
          "url": f"https://space.bilibili.com/{args.mid}"}, args)


def cmd_comments(args):
    vd = fetch_video_data(args.ref)
    aid = vd.get("aid")
    ensure_buvid()
    sort = 2 if args.sort == "hot" else 0
    data = http_json("https://api.bilibili.com/x/v2/reply"
                     f"?type=1&oid={aid}&sort={sort}&pn=1&ps={args.limit}")
    if data.get("code") != 0:
        fail(f"评论获取失败: {data.get('message')}", code="UPSTREAM")
    d = data.get("data") or {}
    items = []
    for r in (d.get("replies") or [])[:args.limit]:
        c = r.get("content") or {}
        items.append({"user": (r.get("member") or {}).get("uname"),
                      "like": r.get("like"), "replies": r.get("rcount"),
                      "text": (c.get("message") or "")[:300],
                      "time": time.strftime(
                          "%Y-%m-%d %H:%M", time.localtime(r["ctime"]))
                      if r.get("ctime") else None})
    emit({"bvid": vd.get("bvid"), "title": vd.get("title"),
          "total_comments": (d.get("page") or {}).get("count"),
          "sort": args.sort, "results": items}, args,
         cols=["user", "like", "text"])


def cmd_subtitle(args):
    apply_auth()
    vd = fetch_video_data(args.ref)
    pages = vd.get("pages") or []
    if not pages:
        fail("该视频无分P信息", code="NOT_FOUND")
    page = pages[min(args.page, len(pages)) - 1]
    cid = page.get("cid")
    ensure_buvid()
    data = http_json("https://api.bilibili.com/x/player/v2?"
                     + urllib.parse.urlencode({"bvid": vd["bvid"], "cid": cid}))
    subs = (((data.get("data") or {}).get("subtitle") or {})
            .get("subtitles") or [])
    if not subs:
        fail("该视频无字幕（或需登录后才有 AI 字幕）：先 bili login qr",
             code="NOT_FOUND")
    chosen = None
    for s in subs:
        if args.lang and s.get("lan", "").startswith(args.lang):
            chosen = s
            break
    chosen = chosen or subs[0]
    url = chosen.get("subtitle_url") or ""
    if url.startswith("//"):
        url = "https:" + url
    raw = http_json(url)
    lines = [{"start": b.get("from"), "end": b.get("to"),
              "text": b.get("content")}
             for b in raw.get("body", [])]
    emit({"bvid": vd["bvid"], "title": vd.get("title"), "cid": cid,
          "page": args.page, "lan": chosen.get("lan"),
          "lan_doc": chosen.get("lan_doc"),
          "available": [{"lan": s.get("lan"), "lan_doc": s.get("lan_doc")}
                        for s in subs],
          "lines": lines,
          "full_text": "".join(l["text"] or "" for l in lines)}, args)


def cmd_danmaku(args):
    apply_auth()
    vd = fetch_video_data(args.ref)
    pages = vd.get("pages") or []
    cid = pages[0].get("cid") if pages else vd.get("cid")
    raw_dm = http_bytes("https://api.bilibili.com/x/v1/dm/list.so?"
                        + urllib.parse.urlencode({"oid": cid}))
    # 弹幕接口返回 raw Deflate 压缩（B站老传统），与 gzip 区分处理
    if raw_dm[:2] != b"\x1f\x8b":
        import zlib
        for wbits in (-15, 15):
            try:
                raw_dm = zlib.decompress(raw_dm, wbits)
                break
            except Exception:
                continue
    xml = raw_dm.decode("utf-8", "ignore")
    items = []
    for m in re.finditer(r'<d p="([^"]+)">(.*?)</d>', xml, re.S):
        f = m.group(1).split(",")
        try:
            t = float(f[0])
        except (ValueError, IndexError):
            continue
        text = re.sub(r"<[^>]+>", "", m.group(2))
        import html as _h
        items.append({"time_sec": t, "text": _h.unescape(text),
                      "sent_at": time.strftime(
                          "%Y-%m-%d %H:%M",
                          time.localtime(int(f[4]))) if len(f) > 4
                      and f[4].isdigit() else None})
    items.sort(key=lambda x: x["time_sec"])
    emit({"bvid": vd["bvid"], "title": vd.get("title"), "cid": cid,
          "total": len(items), "results": items[:args.limit]}, args,
         cols=["time_sec", "text"])


def cmd_me(args):
    require_auth()
    nav = fetch_nav()
    if not nav.get("isLogin"):
        fail("凭据已失效，请重新 bili login qr", code="AUTH")
    emit({"mid": nav.get("mid"), "uname": nav.get("uname"),
          "face": nav.get("face"),
          "level": (nav.get("level_info") or {}).get("current_level"),
          "vip": nav.get("vipStatus") == 1,
          "vip_label": ((nav.get("vip") or {}).get("label") or {}).get("text"),
          "coins": nav.get("money"), "bcoin": nav.get("wallet", {}).get(
              "bcoin_balance") if isinstance(nav.get("wallet"), dict)
          else None,
          "email_verified": nav.get("email_verified") == 1,
          "tel_verified": nav.get("tel_verified") == 1}, args)


def cmd_fav(args):
    require_auth()
    nav = fetch_nav()
    mid = nav.get("mid")
    if args.folder:
        data = http_json("https://api.bilibili.com/x/v3/fav/resource/list?"
                         + urllib.parse.urlencode(
                             {"media_id": args.folder, "pn": 1,
                              "ps": args.limit}))
        if data.get("code") != 0:
            fail(f"收藏夹读取失败: {data.get('message')}", code="UPSTREAM")
        d = data.get("data") or {}
        items = [{"bvid": m.get("bvid") or (m.get("bv_id")),
                  "title": m.get("title"),
                  "author": (m.get("upper") or {}).get("name"),
                  "play": (m.get("cnt_info") or {}).get("play"),
                  "duration_sec": m.get("duration"),
                  "fav_at": time.strftime(
                      "%Y-%m-%d", time.localtime(m["fav_time"]))
                  if m.get("fav_time") else None}
                 for m in d.get("medias") or []]
        emit({"folder_id": args.folder, "title": d.get("info", {}).get(
            "title"), "total": (d.get("info") or {}).get("media_count"),
            "results": items}, args, cols=["bvid", "title", "author", "play"])
    else:
        data = http_json("https://api.bilibili.com/x/v3/fav/folder/created/"
                         "list-all?" + urllib.parse.urlencode({"up_mid": mid}))
        if data.get("code") != 0:
            fail(f"收藏夹列表失败: {data.get('message')}", code="UPSTREAM")
        folders = [{"id": f.get("id"), "title": f.get("title"),
                    "count": f.get("media_count"), "attr": f.get("attr")}
                   for f in (data.get("data") or {}).get("list") or []]
        emit({"mid": mid, "results": folders}, args,
             cols=["id", "title", "count"])


def cmd_history(args):
    require_auth()
    data = http_json("https://api.bilibili.com/x/web-interface/history/cursor?"
                     + urllib.parse.urlencode({"ps": args.limit}))
    if data.get("code") != 0:
        fail(f"历史记录读取失败: {data.get('message')}", code="UPSTREAM")
    items = []
    for it in (data.get("data") or {}).get("list") or []:
        h = it.get("history") or {}
        items.append({"title": it.get("title"), "bvid": h.get("bvid"),
                      "author": it.get("author_name"),
                      "business": h.get("business"),
                      "progress_sec": it.get("progress"),
                      "duration_sec": it.get("duration"),
                      "viewed_at": time.strftime(
                          "%Y-%m-%d %H:%M",
                          time.localtime(it["view_at"]))
                      if it.get("view_at") else None,
                      "url": f"https://www.bilibili.com/video/{h.get('bvid')}"
                      if h.get("bvid") else None})
    emit({"results": items}, args, cols=["viewed_at", "title", "author"])


# ---------------------------------------------------------------- 写操作

def _csrf(auth):
    csrf = (auth.get("cookies") or {}).get("bili_jct")
    if not csrf:
        fail("凭据缺少 bili_jct，请重新 bili login qr", code="AUTH")
    return csrf


def _aid_of(ref):
    vd = fetch_video_data(ref)
    return vd["aid"], vd


def _post_write(url, form, what):
    data = http_post_json(url, form)
    if data.get("code") != 0:
        fail(f"{what}失败: {data.get('message')}（code {data.get('code')}）",
             code="UPSTREAM")
    return data


def cmd_like(args):
    auth = require_auth()
    aid, vd = _aid_of(args.ref)
    _post_write("https://api.bilibili.com/x/web-interface/archive/like",
                {"aid": aid, "like": 2 if args.undo else 1,
                 "csrf": _csrf(auth)}, "点赞")
    emit({"ok": True, "action": "unlike" if args.undo else "like",
          "aid": aid, "bvid": vd["bvid"], "title": vd.get("title")}, args)


def cmd_coin(args):
    auth = require_auth()
    if args.num not in (1, 2):
        fail("--num 只能是 1 或 2", code="INVALID")
    aid, vd = _aid_of(args.ref)
    _post_write("https://api.bilibili.com/x/web-interface/coin/add",
                {"aid": aid, "multiply": args.num, "select_like": 0,
                 "csrf": _csrf(auth)}, "投币")
    emit({"ok": True, "action": "coin", "num": args.num,
          "aid": aid, "bvid": vd["bvid"], "title": vd.get("title")}, args)


def _fav_folder_id(args, mid):
    if args.folder:
        return int(args.folder)
    data = http_json("https://api.bilibili.com/x/v3/fav/folder/created/"
                     "list-all?" + urllib.parse.urlencode({"up_mid": mid}))
    folders = (data.get("data") or {}).get("list") or []
    if not folders:
        fail("没有可用收藏夹", code="UPSTREAM")
    return folders[0]["id"]


def _fav_deal(args, add):
    auth = require_auth()
    nav = fetch_nav()
    if not nav.get("isLogin"):
        fail("凭据已失效，请重新 bili login qr", code="AUTH")
    folder = _fav_folder_id(args, nav.get("mid"))
    aid, vd = _aid_of(args.ref)
    form = {"rid": aid, "type": 2, "csrf": _csrf(auth), "platform": "web"}
    form["add_media_ids" if add else "del_media_ids"] = folder
    _post_write("https://api.bilibili.com/x/v3/fav/resource/deal", form,
                "收藏" if add else "取消收藏")
    emit({"ok": True, "action": "fav_add" if add else "fav_remove",
          "folder_id": folder, "aid": aid, "bvid": vd["bvid"],
          "title": vd.get("title")}, args)


def cmd_favadd(args):
    _fav_deal(args, True)


def cmd_favdel(args):
    _fav_deal(args, False)


def cmd_comment(args):
    auth = require_auth()
    aid, vd = _aid_of(args.ref)
    form = {"oid": aid, "type": 1, "message": args.text, "plat": 1,
            "csrf": _csrf(auth)}
    if args.reply_to:
        form["root"] = args.reply_to
        form["parent"] = args.reply_to
    data = _post_write("https://api.bilibili.com/x/v2/reply/add", form,
                       "发评论")
    rp = (data.get("data") or {}).get("reply") or {}
    emit({"ok": True, "action": "comment", "rpid": rp.get("rpid"),
          "aid": aid, "bvid": vd["bvid"], "text": args.text,
          "note": "评论可能先审后发，列表出现有延迟"}, args)


def cmd_commentdel(args):
    auth = require_auth()
    aid, vd = _aid_of(args.ref)
    _post_write("https://api.bilibili.com/x/v2/reply/del",
                {"oid": aid, "type": 1, "rpid": args.rpid,
                 "csrf": _csrf(auth)}, "删评论")
    emit({"ok": True, "action": "comment_delete", "rpid": int(args.rpid),
          "aid": aid, "bvid": vd["bvid"]}, args)


def cmd_senddm(args):
    auth = require_auth()
    aid, vd = _aid_of(args.ref)
    pages = vd.get("pages") or []
    if args.page < 1 or (pages and args.page > len(pages)):
        fail(f"--page 超出范围（共 {len(pages)} P）", code="INVALID")
    cid = (pages[args.page - 1].get("cid") if pages else vd.get("cid"))
    form = {"aid": aid, "bvid": vd["bvid"], "oid": cid, "type": 1,
            "msg": args.text, "progress": int(args.at * 1000),
            "mode": args.mode, "fontsize": 25, "color": args.color,
            "pool": 0, "rnd": int(time.time()),
            "csrf": _csrf(auth)}
    data = _post_write("https://api.bilibili.com/x/v2/dm/post", form,
                       "发弹幕")
    emit({"ok": True, "action": "danmaku", "dmid": (data.get("data") or {}),
          "aid": aid, "bvid": vd["bvid"], "cid": cid, "text": args.text,
          "at_sec": args.at}, args)


def cmd_follow(args):
    auth = require_auth()
    _post_write("https://api.bilibili.com/x/relation/modify",
                {"fid": args.mid, "act": 2 if args.undo else 1,
                 "re_src": 11, "csrf": _csrf(auth)}, "关注")
    emit({"ok": True, "action": "unfollow" if args.undo else "follow",
          "mid": int(args.mid)}, args)


def cmd_doctor(args):
    checks = []
    for name, fn in (("nav_wbi", lambda: wbi_keys()),
                     ("popular", lambda: http_json(
                         "https://api.bilibili.com/x/web-interface/popular?ps=1")),
                     ("search_wbi", lambda: None),
                     ("video_page", lambda: fetch_video_data("BV1xx411c7mD"))):
        t0 = time.time()
        try:
            if name == "search_wbi":
                ensure_buvid()
                params = wbi_sign({"keyword": "测试", "page": 1,
                                   "search_type": "video"})
                d = http_json("https://api.bilibili.com/x/web-interface/"
                              "wbi/search/all/v2?" + urllib.parse.urlencode(params))
                if d.get("code") != 0:
                    raise RuntimeError(d.get("message"))
            else:
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
    {"name": "search", "usage": "bili search <关键词> [--limit N] "
     "[--order totalrank|click|pubdate|dm|stow]",
     "desc": "视频搜索（WBI 签名自动处理）"},
    {"name": "video", "usage": "bili video <BV号|av号|链接>",
     "desc": "视频详情：标题/UP/播放弹幕评论收藏投币分享赞/分P/简介"},
    {"name": "rank", "usage": "bili rank [--rid 分区] [--limit N]",
     "desc": "全站排行榜（rid=0 全站）"},
    {"name": "popular", "usage": "bili popular [--limit N]", "desc": "热门视频"},
    {"name": "up", "usage": "bili up <mid>", "desc": "UP主信息（粉丝/获赞/稿件数）"},
    {"name": "comments", "usage": "bili comments <BV号> [--sort hot|time] [--limit N]",
     "desc": "热门/最新评论"},
    {"name": "login qr", "usage": "bili login qr",
     "desc": "生成扫码登录二维码（PNG 路径输出，约 180 秒有效）"},
    {"name": "login poll", "usage": "bili login poll",
     "desc": "轮询扫码状态；成功后凭据存 ~/.bili_auth.json（0600）"},
    {"name": "login status", "usage": "bili login status", "desc": "登录状态"},
    {"name": "login logout", "usage": "bili login logout", "desc": "退出并清除凭据"},
    {"name": "subtitle", "usage": "bili subtitle <BV号> [--page N] [--lang zh]",
     "desc": "视频字幕全文（含 AI 字幕，一般需先登录）"},
    {"name": "danmaku", "usage": "bili danmaku <BV号> [--limit N]",
     "desc": "弹幕列表（时间轴/内容/发送时间）"},
    {"name": "me", "usage": "bili me", "desc": "我的账号信息（需登录）"},
    {"name": "fav", "usage": "bili fav [--folder <id>] [--limit N]",
     "desc": "我的收藏夹列表 / 夹内视频（需登录）"},
    {"name": "history", "usage": "bili history [--limit N]",
     "desc": "观看历史（需登录）"},
    {"name": "like", "usage": "bili like <BV号> [--undo]",
     "desc": "点赞 / 取消点赞（写操作，需登录）"},
    {"name": "coin", "usage": "bili coin <BV号> [--num 1|2]",
     "desc": "投币（写操作，不可撤销，需登录）"},
    {"name": "favadd", "usage": "bili favadd <BV号> [--folder <id>]",
     "desc": "收藏到收藏夹（默认第一个收藏夹；写操作，需登录）"},
    {"name": "favdel", "usage": "bili favdel <BV号> [--folder <id>]",
     "desc": "取消收藏（写操作，需登录）"},
    {"name": "follow", "usage": "bili follow <mid> [--undo]",
     "desc": "关注 / 取关 UP主（写操作，需登录）"},
    {"name": "comment", "usage": "bili comment <BV号> <文本> [--reply-to <rpid>]",
     "desc": "发评论 / 回复评论（写操作，需登录；可能先审后发）"},
    {"name": "commentdel", "usage": "bili commentdel <BV号> <rpid>",
     "desc": "删除自己的评论（写操作，需登录）"},
    {"name": "senddm", "usage": "bili senddm <BV号> <文本> [--at 秒] "
     "[--page N] [--mode 1|4|5] [--color 十进制]",
     "desc": "发弹幕（写操作，需登录；发送后不可撤回）"},
    {"name": "doctor", "usage": "bili doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "bili commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "无需登录；字幕/弹幕正文不在本版范围；错误带 code"},
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
    p = argparse.ArgumentParser(prog="bili", description="哔哩哔哩查询 CLI（公开接口，免登录）")
    p.add_argument("--version", action="version", version=f"bili {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="视频搜索")
    sp.add_argument("keyword")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--order", default="totalrank")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("video", help="视频详情")
    sp.add_argument("ref")
    sp.set_defaults(func=cmd_video)

    sp = sub.add_parser("rank", help="全站排行榜")
    sp.add_argument("--rid", type=int, default=0)
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_rank)

    sp = sub.add_parser("popular", help="热门视频")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_popular)

    sp = sub.add_parser("up", help="UP主信息")
    sp.add_argument("mid")
    sp.set_defaults(func=cmd_up)

    sp = sub.add_parser("comments", help="视频评论")
    sp.add_argument("ref")
    sp.add_argument("--sort", default="hot", choices=["hot", "time"])
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_comments)

    sp = sub.add_parser("login", help="扫码登录（子命令 qr/poll/status/logout）")
    sp.add_argument("action", choices=["qr", "poll", "status", "logout"])
    sp.set_defaults(func=lambda a: {"qr": cmd_login_qr, "poll": cmd_login_poll,
                                    "status": cmd_login_status,
                                    "logout": cmd_login_logout}[a.action](a))

    sp = sub.add_parser("subtitle", help="视频字幕（需登录获取 AI 字幕）")
    sp.add_argument("ref")
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--lang", default="zh")
    sp.set_defaults(func=cmd_subtitle)

    sp = sub.add_parser("danmaku", help="弹幕列表")
    sp.add_argument("ref")
    sp.add_argument("--limit", type=int, default=500)
    sp.set_defaults(func=cmd_danmaku)

    sp = sub.add_parser("me", help="我的账号信息（需登录）")
    sp.set_defaults(func=cmd_me)

    sp = sub.add_parser("fav", help="我的收藏夹（需登录）")
    sp.add_argument("--folder", default=None)
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_fav)

    sp = sub.add_parser("like", help="点赞/取消点赞（需登录）")
    sp.add_argument("ref")
    sp.add_argument("--undo", action="store_true")
    sp.set_defaults(func=cmd_like)

    sp = sub.add_parser("coin", help="投币（需登录，不可撤销）")
    sp.add_argument("ref")
    sp.add_argument("--num", type=int, default=1)
    sp.set_defaults(func=cmd_coin)

    sp = sub.add_parser("favadd", help="收藏视频（需登录）")
    sp.add_argument("ref")
    sp.add_argument("--folder", default=None)
    sp.set_defaults(func=cmd_favadd)

    sp = sub.add_parser("favdel", help="取消收藏（需登录）")
    sp.add_argument("ref")
    sp.add_argument("--folder", default=None)
    sp.set_defaults(func=cmd_favdel)

    sp = sub.add_parser("follow", help="关注/取关 UP主（需登录）")
    sp.add_argument("mid")
    sp.add_argument("--undo", action="store_true")
    sp.set_defaults(func=cmd_follow)

    sp = sub.add_parser("comment", help="发评论（需登录）")
    sp.add_argument("ref")
    sp.add_argument("text")
    sp.add_argument("--reply-to", type=int, default=None)
    sp.set_defaults(func=cmd_comment)

    sp = sub.add_parser("commentdel", help="删除自己的评论（需登录）")
    sp.add_argument("ref")
    sp.add_argument("rpid")
    sp.set_defaults(func=cmd_commentdel)

    sp = sub.add_parser("senddm", help="发弹幕（需登录，不可撤回）")
    sp.add_argument("ref")
    sp.add_argument("text")
    sp.add_argument("--at", type=float, default=0.0)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--mode", type=int, default=1)
    sp.add_argument("--color", type=int, default=16777215)
    sp.set_defaults(func=cmd_senddm)

    sp = sub.add_parser("history", help="观看历史（需登录）")
    sp.add_argument("--limit", type=int, default=20)
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
            code = {404: "NOT_FOUND", 412: "BLOCKED",
                    429: "RATE_LIMIT"}.get(
                e.code, "UPSTREAM" if e.code >= 500 else "HTTP")
        elif isinstance(e, urllib.error.URLError):
            code = "NETWORK"
        elif isinstance(e, RuntimeError):
            code = "UPSTREAM"
        fail(str(e), code=code)


if __name__ == "__main__":
    main()
