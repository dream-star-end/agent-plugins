#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
netease — 网易云音乐元数据 CLI（供 AI agent / 脚本调用）

数据源：网易云音乐 /api 明文兼容面（2019 Linux 客户端接口面，匿名免登录）
  * 搜索    POST /api/cloudsearch/pc
  * 歌曲    POST /api/v3/song/detail （c=[{id,v:0}]）
  * 歌词    GET  /api/song/lyric （os=linux）
  * 歌单    GET  /api/v3/playlist/detail
  * 歌手    GET  /api/v1/artist/{id}、/api/artist/albums、/api/artist/introduction
  * 专辑    GET  /api/v1/album/{id}
  * 榜单    GET  /api/toplist
  * 推荐    GET  /api/personalized/playlist

仅做元数据与歌词：不给播放地址、不下载、不登录。
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
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BASE = "https://music.163.com"
TIMEOUT = 25
VERSION = "1.0.0"
MIN_INTERVAL = 0.45  # 匿名低频节流（普查以 1.2s 间隔无风控迹象）
_TZ = timezone(timedelta(hours=8))
_last_req = [0.0]

SEARCH_TYPES = {"song": 1, "artist": 100, "album": 10,
                "playlist": 1000, "lyric": 1006}


def fail(msg, code="ERROR"):
    print(json.dumps({"error": msg, "code": code}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def http_json(path, params=None, post=None):
    """带节流 + 重试的请求；统一校验网易云业务 code。"""
    url = BASE + path
    data = None
    headers = {"User-Agent": UA, "Referer": "https://music.163.com/"}
    if post is not None:
        data = urllib.parse.urlencode(post).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif params:
        url += "?" + urllib.parse.urlencode(params)
    last_exc = None
    for attempt in range(3):
        wait = MIN_INTERVAL - (time.time() - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                _last_req[0] = time.time()
                body = resp.read().decode("utf-8", errors="ignore")
            data_json = json.loads(body)
        except urllib.error.HTTPError as e:
            _last_req[0] = time.time()
            if e.code in (502, 503, 504) and attempt < 2:
                last_exc = e
                time.sleep(0.7 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, ValueError) as e:
            _last_req[0] = time.time()
            if attempt < 2:
                last_exc = e
                time.sleep(0.7 * (attempt + 1))
                continue
            raise RuntimeError(f"请求失败: {e}")
        code = data_json.get("code")
        if code is not None and code != 200:
            if code == 404:
                fail(f"网易云无此资源（code=404）: {path}", code="NOT_FOUND")
            raise RuntimeError(
                f"网易云返回业务错误 code={code}: "
                f"{data_json.get('msg') or data_json.get('message') or ''}")
        return data_json
    raise last_exc


# ---------------------------------------------------------------- shaping

def _dur(ms):
    if not ms:
        return None
    sec = int(ms) // 1000
    return f"{sec // 60}:{sec % 60:02d}"


def _date(ms):
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=_TZ).strftime("%Y-%m-%d")


def shape_song(s):
    ars = [{"id": a.get("id"), "name": a.get("name")}
           for a in (s.get("ar") or s.get("artists") or [])]
    al = s.get("al") or s.get("album") or {}
    return {
        "id": s.get("id"),
        "name": s.get("name"),
        "artist": " / ".join(a["name"] for a in ars if a.get("name")),
        "artists": ars,
        "album": al.get("name"),
        "album_id": al.get("id"),
        "pic_url": al.get("picUrl"),
        "duration_ms": s.get("dt"),
        "duration": _dur(s.get("dt")),
        "alias": s.get("alia") or [],
        "fee": s.get("fee"),
        "mv": s.get("mv"),
        "pop": s.get("pop"),
        "publish_date": _date(s.get("publishTime")),
    }


def shape_artist(a):
    return {
        "id": a.get("id"),
        "name": a.get("name"),
        "alias": a.get("alias") or a.get("alia") or [],
        "music_size": a.get("musicSize"),
        "album_size": a.get("albumSize"),
        "mv_size": a.get("mvSize"),
        "pic_url": a.get("picUrl") or a.get("img1v1Url"),
        "brief_desc": a.get("briefDesc"),
    }


def shape_album(a):
    ars = [{"id": x.get("id"), "name": x.get("name")}
           for x in (a.get("artists") or [])]
    if not ars and a.get("artist"):
        ars = [{"id": a["artist"].get("id"), "name": a["artist"].get("name")}]
    return {
        "id": a.get("id"),
        "name": a.get("name"),
        "artist": " / ".join(x["name"] for x in ars if x.get("name")),
        "artists": ars,
        "publish_date": _date(a.get("publishTime")),
        "size": a.get("size"),
        "type": a.get("type"),
        "sub_type": a.get("subType"),
        "company": a.get("company"),
        "pic_url": a.get("picUrl"),
        "alias": a.get("alias") or [],
        "description": a.get("description") or a.get("briefDesc"),
    }


def shape_playlist_brief(p):
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "track_count": p.get("trackCount"),
        "play_count": p.get("playCount"),
        "creator": (p.get("creator") or {}).get("nickname"),
        "cover": p.get("coverImgUrl") or p.get("picUrl"),
        "description": p.get("description"),
        "copywriter": p.get("copywriter"),
    }


def fetch_songs(ids):
    """批量歌曲详情（/api/v3/song/detail，每批 100 个 id）。"""
    out = []
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        c = json.dumps([{"id": int(x), "v": 0} for x in chunk])
        data = http_json("/api/v3/song/detail/", post={"c": c})
        out.extend(shape_song(s) for s in (data.get("songs") or []))
    return out


# ---------------------------------------------------------------- commands

def cmd_search(args):
    tname = args.type
    data = http_json("/api/cloudsearch/pc", post={
        "s": args.keyword, "type": SEARCH_TYPES[tname],
        "limit": args.limit, "offset": 0})
    res = data.get("result") or {}
    out = {"query": args.keyword, "type": tname}
    if tname in ("song", "lyric"):
        songs = [shape_song(s) for s in (res.get("songs") or [])]
        if tname == "lyric":
            for row, raw in zip(songs, res.get("songs") or []):
                lyr = raw.get("lyrics") or []
                import re
                row["matched_lyrics"] = [re.sub(r"</?b>", "", x)
                                         for x in lyr]
        out["count"] = res.get("songCount")
        out["results"] = songs
        if tname == "song":
            out["note"] = ("匿名态单曲排序与官方客户端不一致：版权曲可能"
                           "沉底，原版未必置顶；计数真实。歌手/歌单搜索精准")
    elif tname == "artist":
        out["count"] = res.get("artistCount")
        out["results"] = [shape_artist(a) for a in (res.get("artists") or [])]
    elif tname == "album":
        out["count"] = res.get("albumCount")
        out["results"] = [shape_album(a) for a in (res.get("albums") or [])]
    else:  # playlist
        out["count"] = res.get("playlistCount")
        out["results"] = [shape_playlist_brief(p)
                          for p in (res.get("playlists") or [])]
    emit(out, args, cols=["id", "name", "artist", "album", "duration"])


def cmd_song(args):
    ids = []
    for x in args.ids:
        if not str(x).isdigit():
            fail(f"歌曲 id 应为数字: {x}", code="INVALID")
        ids.append(int(x))
    songs = fetch_songs(ids)
    if not songs:
        fail(f"查不到歌曲: {args.ids}", code="NOT_FOUND")
    emit({"count": len(songs), "songs": songs}, args,
         cols=["id", "name", "artist", "album", "duration"])


def cmd_lyric(args):
    if not str(args.id).isdigit():
        fail(f"歌曲 id 应为数字: {args.id}", code="INVALID")
    data = http_json("/api/song/lyric", params={
        "os": "linux", "id": args.id, "lv": -1, "kv": -1, "tv": -1})
    lrc = (data.get("lrc") or {}).get("lyric") or ""
    if not lrc:
        fail(f"歌曲 {args.id} 暂无歌词", code="NOT_FOUND")
    tlyric = (data.get("tlyric") or {}).get("lyric") or None
    klyric = (data.get("klyric") or {}).get("lyric") or None
    user = (data.get("lyricUser") or {}).get("nickname")
    emit({"id": int(args.id), "lrc": lrc, "tlyric": tlyric,
          "klyric": klyric, "lyric_user": user}, args)


def cmd_playlist(args):
    if not str(args.id).isdigit():
        fail(f"歌单 id 应为数字: {args.id}", code="INVALID")
    data = http_json("/api/v3/playlist/detail", params={
        "id": args.id, "n": 100000, "s": 8, "t": 0})
    pl = data.get("playlist")
    if not pl:
        fail(f"查不到歌单: {args.id}", code="NOT_FOUND")
    info = shape_playlist_brief(pl)
    info["tags"] = pl.get("tags")
    info["create_date"] = _date(pl.get("createTime"))
    info["update_date"] = _date(pl.get("updateTime"))
    embedded = [shape_song(s) for s in (pl.get("tracks") or [])]
    tracks = embedded[:args.limit]
    if len(tracks) < args.limit:
        have = {t["id"] for t in embedded}
        rest = [tid.get("id") for tid in (pl.get("trackIds") or [])
                if tid.get("id") not in have]
        need = args.limit - len(tracks)
        if rest and need > 0:
            tracks.extend(fetch_songs(rest[:need]))
    emit({"playlist": info, "tracks_total": pl.get("trackCount"),
          "tracks_returned": len(tracks), "tracks": tracks}, args,
         cols=["id", "name", "artist", "album", "duration"])


def cmd_artist(args):
    if not str(args.id).isdigit():
        fail(f"歌手 id 应为数字: {args.id}", code="INVALID")
    data = http_json(f"/api/v1/artist/{args.id}",
                     params={"ext": "true", "private_cloud": "true"})
    art = data.get("artist")
    if not art:
        fail(f"查不到歌手: {args.id}", code="NOT_FOUND")
    out = {"artist": shape_artist(art),
           "hot_songs": [shape_song(s) for s in (data.get("hotSongs") or [])]}
    if args.with_ == "albums":
        d2 = http_json(f"/api/artist/albums/{args.id}",
                       params={"limit": 30, "offset": 0})
        out["albums"] = [shape_album(a) for a in (d2.get("hotAlbums") or [])]
    elif args.with_ == "intro":
        d2 = http_json("/api/artist/introduction", params={"id": args.id})
        out["introduction"] = [
            {"title": x.get("ti"), "text": x.get("txt")}
            for x in (d2.get("introduction") or [])]
    emit(out, args, cols=["id", "name", "artist", "album", "duration"])


def cmd_album(args):
    if not str(args.id).isdigit():
        fail(f"专辑 id 应为数字: {args.id}", code="INVALID")
    data = http_json(f"/api/v1/album/{args.id}",
                     params={"ext": "true", "private_cloud": "true"})
    al = data.get("album")
    if not al:
        fail(f"查不到专辑: {args.id}", code="NOT_FOUND")
    emit({"album": shape_album(al),
          "songs": [shape_song(s) for s in (data.get("songs") or [])]}, args,
         cols=["id", "name", "artist", "duration"])


def cmd_toplist(args):
    data = http_json("/api/toplist")
    lists = []
    for p in (data.get("list") or []):
        row = shape_playlist_brief(p)
        row["update_frequency"] = p.get("updateFrequency")
        lists.append(row)
    at = data.get("artistToplist") or {}
    emit({"lists": lists,
          "artist_toplist": {"name": at.get("name"),
                             "update_frequency": at.get("updateFrequency"),
                             "position": at.get("position"),
                             "cover": at.get("coverUrl")}}, args,
         cols=["id", "name", "track_count", "play_count", "update_frequency"])


def cmd_recommend(args):
    data = http_json("/api/personalized/playlist",
                     params={"limit": args.limit})
    rows = [shape_playlist_brief(p) for p in (data.get("result") or [])]
    emit({"results": rows}, args,
         cols=["id", "name", "track_count", "play_count"])


def cmd_doctor(args):
    checks = []
    song_id = None
    t0 = time.time()
    try:
        d = http_json("/api/cloudsearch/pc", post={
            "s": "周杰伦 晴天", "type": 1, "limit": 3, "offset": 0})
        songs = (d.get("result") or {}).get("songs") or []
        if not songs:
            raise RuntimeError("cloudsearch 返回空结果")
        song_id = songs[0].get("id")
        checks.append({"name": "cloudsearch", "ok": True,
                       "ms": int((time.time() - t0) * 1000),
                       "detail": f"歌曲搜索命中，首曲 id={song_id}"})
    except Exception as e:
        checks.append({"name": "cloudsearch", "ok": False,
                       "ms": int((time.time() - t0) * 1000),
                       "detail": str(e)[:160]})
    t0 = time.time()
    try:
        if song_id is None:
            raise RuntimeError("cloudsearch 未给出歌曲 id，跳过歌词探针")
        d = http_json("/api/song/lyric", params={
            "os": "linux", "id": song_id, "lv": -1, "kv": -1, "tv": -1})
        has = bool((d.get("lrc") or {}).get("lyric"))
        checks.append({"name": "lyric", "ok": True,
                       "ms": int((time.time() - t0) * 1000),
                       "detail": f"id={song_id} 歌词{'有' if has else '为空'}"})
    except Exception as e:
        checks.append({"name": "lyric", "ok": False,
                       "ms": int((time.time() - t0) * 1000),
                       "detail": str(e)[:160]})
    ok = all(c["ok"] for c in checks)
    emit({"ok": ok, "checks": checks}, args)
    if not ok:
        sys.exit(1)


COMMANDS_MANIFEST = [
    {"name": "search", "usage": "netease search <关键词> "
     "[--type song|artist|album|playlist|lyric] [--limit N]",
     "desc": "搜索歌曲/歌手/专辑/歌单/歌词（单曲排序与官方客户端不一致，见 README）"},
    {"name": "song", "usage": "netease song <id...>",
     "desc": "批量歌曲详情（歌名/歌手/专辑/时长/别名）"},
    {"name": "lyric", "usage": "netease lyric <id>",
     "desc": "歌词 LRC 原文 + 翻译歌词（有则给）"},
    {"name": "playlist", "usage": "netease playlist <id> [--limit N]",
     "desc": "歌单信息 + 曲目列表（超出内嵌部分自动批量补全详情）"},
    {"name": "artist", "usage": "netease artist <id> [--with albums|intro]",
     "desc": "歌手资料 + 热门歌曲；可选附专辑列表或歌手介绍"},
    {"name": "album", "usage": "netease album <id>",
     "desc": "专辑信息 + 全部曲目"},
    {"name": "toplist", "usage": "netease toplist", "desc": "官方榜单目录"},
    {"name": "recommend", "usage": "netease recommend [--limit N]",
     "desc": "匿名推荐歌单"},
    {"name": "doctor", "usage": "netease doctor",
     "desc": "通道健康检查（cloudsearch + lyric 双探针）"},
    {"name": "commands", "usage": "netease commands", "desc": "能力清单"},
]


def cmd_commands(args):
    emit({"commands": COMMANDS_MANIFEST,
          "conventions": "默认 JSON；--table/--compact/--fields 全局选项；"
                         "匿名免登录，仅元数据与歌词，无播放地址；"
                         "错误带 code"}, args)


# ---------------------------------------------------------------- output

_LIST_KEYS = ("results", "songs", "tracks", "hot_songs", "lists",
              "albums", "checks")


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
        prog="netease", description="网易云音乐元数据 CLI（匿名明文 /api 面）")
    p.add_argument("--version", action="version",
                   version=f"netease {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="搜索")
    sp.add_argument("keyword")
    sp.add_argument("--type", choices=list(SEARCH_TYPES), default="song")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("song", help="批量歌曲详情")
    sp.add_argument("ids", nargs="+")
    sp.set_defaults(func=cmd_song)

    sp = sub.add_parser("lyric", help="歌词")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_lyric)

    sp = sub.add_parser("playlist", help="歌单详情+曲目")
    sp.add_argument("id")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_playlist)

    sp = sub.add_parser("artist", help="歌手资料+热门歌曲")
    sp.add_argument("id")
    sp.add_argument("--with", dest="with_", choices=["albums", "intro"],
                    default=None)
    sp.set_defaults(func=cmd_artist)

    sp = sub.add_parser("album", help="专辑信息+曲目")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_album)

    sp = sub.add_parser("toplist", help="官方榜单目录")
    sp.set_defaults(func=cmd_toplist)

    sp = sub.add_parser("recommend", help="匿名推荐歌单")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_recommend)

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
