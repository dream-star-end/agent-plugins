#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zhihu — 知乎查询 CLI（供 AI agent / 脚本调用）

登录方式说明（重要）：知乎网页版二维码登录接口带设备指纹签名
（d_c0/x-zse），无法像 B站/微博那样纯 API 扫码。因此本插件的登录是
**cookie 登录**：用户在浏览器登录 zhihu.com 后复制 z_c0 cookie 值，
用 `zhihu login set` 存入本机 ~/.zhihu_auth.json（0600）。
带 z_c0 后调用知乎 v4 API（搜索/问题/回答/用户/收藏）。

热榜在 hot 插件里（免登录），本插件不重复。

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

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/126 Safari/537.36")
TIMEOUT = 25
VERSION = "1.0.0"
AUTH_FILE = os.path.join(os.path.expanduser("~"), ".zhihu_auth.json")
API = "https://www.zhihu.com/api/v4"


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def load_auth():
    if not os.path.exists(AUTH_FILE):
        return None
    try:
        with open(AUTH_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def http_json(url, auth_required=True, raw=False):
    auth = load_auth()
    if auth_required and not auth:
        fail("未登录：先运行 zhihu login set（粘贴浏览器里的 z_c0 cookie）",
             code="AUTH")
    headers = {"User-Agent": UA, "Referer": "https://www.zhihu.com/"}
    if auth:
        headers["Cookie"] = "; ".join(
            f"{k}={v}" for k, v in (auth.get("cookies") or {}).items())
    last = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
            # 知乎的业务错误以 HTTP 200 + {"error": {...}} 返回，不拦会污染解析
            if not raw and isinstance(data, dict) and data.get("error"):
                err = data["error"] or {}
                fail(f"知乎接口错误: {err.get('message')}（code "
                     f"{err.get('code')}）", code="UPSTREAM")
            return data
        except urllib.error.HTTPError as e:
            if e.code == 403:
                fail("知乎拒绝访问（403）：z_c0 可能已失效，重新 login set",
                     code="AUTH")
            last = e
            if e.code not in (502, 503, 504):
                raise
        except urllib.error.URLError as e:
            last = e
        time.sleep(0.8)
    raise last


def strip_html(html):
    text = re.sub(r"<[^>]+>", " ", html or "")
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(text)).strip()


# ---------------------------------------------------------------- login

def cmd_login_set(args):
    raw = args.cookie.strip()
    if raw == "-":  # 从 stdin 读，避免凭据出现在进程参数里
        raw = sys.stdin.read().strip()
    elif raw.startswith("@"):  # 从文件读
        with open(raw[1:], encoding="utf-8") as f:
            raw = f.read().strip()
    cookies = {}
    for part in raw.replace("\n", ";").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    if "z_c0" not in cookies and "=" not in raw:
        cookies = {"z_c0": raw}
    elif "z_c0" not in cookies and "=" in raw and not raw.startswith("z_c0"):
        # 用户可能只粘了值本身（无键名、无分号）时上面的分支已处理；
        # 这里兜底：整串当 z_c0
        if len(cookies) == 0:
            cookies = {"z_c0": raw}
    if "z_c0" not in cookies:
        fail("没找到 z_c0：请粘贴完整的 Cookie 串或单独的 z_c0 值",
             code="INVALID")
    auth = {"cookies": cookies,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(auth, f, ensure_ascii=False)
    os.chmod(AUTH_FILE, 0o600)
    me = http_json(f"{API}/me", auth_required=False, raw=True) \
        if load_auth() else {}
    emit({"saved": True, "cookies": sorted(cookies),
          "me": {"name": me.get("name"), "url_token": me.get("url_token")}
          if me else None}, args)


def cmd_login_status(args):
    auth = load_auth()
    if not auth:
        emit({"logged_in": False}, args)
        return
    try:
        me = http_json(f"{API}/me", auth_required=False, raw=True)
        ok = bool(me.get("id"))
    except SystemExit:
        raise
    except Exception:
        ok, me = False, {}
    emit({"logged_in": ok, "name": me.get("name"),
          "url_token": me.get("url_token"),
          "saved_at": auth.get("saved_at"),
          "note": None if ok else "凭据可能已失效"}, args)


def cmd_login_logout(args):
    if os.path.exists(AUTH_FILE):
        os.remove(AUTH_FILE)
    emit({"logged_out": True}, args)


# ---------------------------------------------------------------- content

def cmd_me(args):
    me = http_json(f"{API}/me")
    followers = me.get("follower_count")
    if followers is None and me.get("url_token"):
        # 实测 /me 不返回 follower_count，members?include 才给（2026-10-12 验）
        u = http_json(f"{API}/members/{me['url_token']}"
                      "?include=follower_count")
        followers = u.get("follower_count")
    emit({"id": me.get("id"), "url_token": me.get("url_token"),
          "name": me.get("name"), "headline": me.get("headline"),
          "followers": followers,
          "answers": me.get("answer_count"),
          "articles": me.get("articles_count"),
          "voteups": me.get("voteup_count"),
          "url": f"https://www.zhihu.com/people/{me.get('url_token')}"},
         args)


def _search_title(obj):
    if obj.get("title"):
        return strip_html(obj["title"])
    q = obj.get("question")
    if isinstance(q, dict) and q.get("name"):
        return strip_html(q["name"])
    return None


def cmd_search(args):
    q = urllib.parse.urlencode({"t": "general", "q": args.query,
                                "correction": 1, "offset": 0,
                                "limit": args.limit, "show_all_topics": 0})
    data = http_json(f"https://www.zhihu.com/api/v4/search_v3?{q}")
    items = []
    for it in data.get("data") or []:
        obj = it.get("object") or {}
        author = obj.get("author") or {}
        items.append({
            "type": it.get("type") or obj.get("type"),
            "title": _search_title(obj),
            "excerpt": strip_html(obj.get("excerpt"))[:200] or None,
            "author": author.get("name") if isinstance(author, dict)
            else None,
            "voteups": obj.get("voteup_count"),
            "url": obj.get("url")})
    emit({"query": args.query, "results": items[:args.limit]}, args,
         cols=["type", "title", "author", "voteups"])


def cmd_question(args):
    qid = re.sub(r"\D", "", args.ref) or args.ref
    # 裸 /questions/{id} 实测返回 10003（参数异常），官方已不可用；
    # 改走回答接口：标题/创建时间在每条回答的 question 对象里，
    # 回答总数在 paging.totals 里（2026-10-12 用真实登录态响应验证）
    limit = args.limit if args.with_answers else 1
    ans = http_json(
        f"{API}/questions/{qid}/answers?include=data%5B*%5D.content"
        f",data%5B*%5D.voteup_count&limit={limit}&offset=0&sort_by=default")
    rows = ans.get("data") or []
    qobj = (rows[0].get("question") or {}) if rows else {}
    out = {"id": int(qid) if str(qid).isdigit() else qid,
           "title": qobj.get("title"),
           "answers": (ans.get("paging") or {}).get("totals"),
           "created": time.strftime("%Y-%m-%d",
                                    time.localtime(qobj["created"]))
           if qobj.get("created") else None,
           "url": f"https://www.zhihu.com/question/{qid}",
           "note": None if rows else "该问题暂无回答或不存在，标题无从取得"}
    if args.with_answers:
        out["top_answers"] = [
            {"author": (a.get("author") or {}).get("name"),
             "voteups": a.get("voteup_count"),
             "text": strip_html(a.get("content"))[:600]}
            for a in rows]
    emit(out, args)


def cmd_user(args):
    # 基础 members 响应不含计数，必须 include（2026-10-12 实测）
    u = http_json(f"{API}/members/{args.token}?include=answer_count,"
                  "articles_count,follower_count,following_count,"
                  "voteup_count")
    emit({"url_token": u.get("url_token"), "name": u.get("name"),
          "headline": u.get("headline"),
          "followers": u.get("follower_count"),
          "following": u.get("following_count"),
          "answers": u.get("answer_count"),
          "articles": u.get("articles_count"),
          "voteups": u.get("voteup_count"),
          "url": f"https://www.zhihu.com/people/{args.token}"}, args)


def cmd_fav(args):
    me = http_json(f"{API}/me")
    token = me.get("url_token")
    data = http_json(f"{API}/members/{token}/favlists")
    # 实测 favlists 只给 id/title/is_public/url，不提供计数（include 无效）
    items = [{"id": f.get("id"), "title": f.get("title"),
              "is_public": f.get("is_public"), "url": f.get("url")}
             for f in data.get("data") or []]
    emit({"me": me.get("name"), "results": items}, args,
         cols=["id", "title", "is_public"])


def cmd_doctor(args):
    checks = []
    t0 = time.time()
    try:
        import urllib.request as _u
        req = _u.Request("https://api.zhihu.com/topstory/hot-lists/total?limit=1",
                         headers={"User-Agent": UA})
        with _u.urlopen(req, timeout=TIMEOUT) as r:
            json.loads(r.read().decode("utf-8", "ignore"))
        checks.append({"name": "public_api", "ok": True,
                       "ms": int((time.time() - t0) * 1000)})
    except Exception as e:
        checks.append({"name": "public_api", "ok": False,
                       "ms": int((time.time() - t0) * 1000),
                       "detail": str(e)[:120]})
    auth = load_auth()
    checks.append({"name": "auth_cookie", "ok": bool(auth),
                   "detail": None if auth else "未设置 z_c0（zhihu login set）"})
    emit({"ok": checks[0]["ok"],
          "note": "内容解析已于 2026-10-12 用真实登录态响应逐字段验证并修正"
                  "（question 改走回答接口、user/me 补 include、fav 按实测字段）；"
                  "CLI 端到端仍待 z_c0 落盘后复验",
          "checks": checks}, args)


COMMANDS_MANIFEST = [
    {"name": "login set", "usage": "zhihu login set <Cookie串|-|@文件>",
     "desc": "保存知乎登录 cookie 到 ~/.zhihu_auth.json；- 表示从 stdin 读、"
             "@文件 表示从文件读（agent 从浏览器取 cookie 后用此落盘）"},
    {"name": "login status", "usage": "zhihu login status", "desc": "登录状态校验"},
    {"name": "login logout", "usage": "zhihu login logout", "desc": "清除凭据"},
    {"name": "me", "usage": "zhihu me", "desc": "我的知乎资料（需登录）"},
    {"name": "search", "usage": "zhihu search <关键词> [--limit N]",
     "desc": "综合搜索（问题/回答/文章，需登录）"},
    {"name": "question", "usage": "zhihu question <问题ID|链接> [--answers] [--limit N]",
     "desc": "问题标题/回答数（取自回答接口），可附高赞回答"},
    {"name": "user", "usage": "zhihu user <url_token>", "desc": "用户资料"},
    {"name": "fav", "usage": "zhihu fav", "desc": "我的收藏夹列表（需登录）"},
    {"name": "doctor", "usage": "zhihu doctor", "desc": "通道健康检查"},
    {"name": "commands", "usage": "zhihu commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "登录为 cookie 方式（知乎扫码接口有签名墙）；"
                         "错误带 code"}, args)


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
    p = argparse.ArgumentParser(prog="zhihu", description="知乎查询 CLI（cookie 登录）")
    p.add_argument("--version", action="version", version=f"zhihu {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("login", help="cookie 登录（子命令 set/status/logout）")
    sp.add_argument("action", choices=["set", "status", "logout"])
    sp.add_argument("cookie", nargs="?", default="")
    sp.set_defaults(func=lambda a: (
        cmd_login_set(a) if a.action == "set" else
        cmd_login_status(a) if a.action == "status" else
        cmd_login_logout(a)))

    sp = sub.add_parser("me", help="我的资料（需登录）")
    sp.set_defaults(func=cmd_me)

    sp = sub.add_parser("search", help="综合搜索（需登录）")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("question", help="问题详情")
    sp.add_argument("ref")
    sp.add_argument("--answers", dest="with_answers", action="store_true")
    sp.add_argument("--limit", type=int, default=5)
    sp.set_defaults(func=cmd_question)

    sp = sub.add_parser("user", help="用户资料")
    sp.add_argument("token")
    sp.set_defaults(func=cmd_user)

    sp = sub.add_parser("fav", help="我的收藏夹（需登录）")
    sp.set_defaults(func=cmd_fav)

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
            code = {403: "AUTH", 404: "NOT_FOUND",
                    429: "RATE_LIMIT"}.get(
                e.code, "UPSTREAM" if e.code >= 500 else "HTTP")
        elif isinstance(e, urllib.error.URLError):
            code = "NETWORK"
        elif isinstance(e, RuntimeError):
            code = "UPSTREAM"
        fail(str(e), code=code)


if __name__ == "__main__":
    main()
