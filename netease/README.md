# netease-plugin · 网易云音乐元数据 Agent 插件

给 AI Agent 用的网易云音乐检索工具包：**零依赖 CLI + Agent Skill**。
走的是网易云 `/api` 明文兼容面（2019 Linux 客户端接口面），
**匿名免登录、无 Cookie**，2026-10-12 逐端点普查实测存活。

**定位是元数据与歌词检索**：搜索、歌曲/歌手/专辑/歌单/榜单信息、歌词全文。
不是播放器——不提供播放地址、不下载音乐、不做登录。

| 命令 | 说明 |
|---|---|
| `netease search <关键词> [--type song\|artist\|album\|playlist\|lyric] [--limit N]` | 搜索（默认找歌）；歌词搜索返回歌词含关键词的歌曲及命中歌词行 |
| `netease song <id...>` | 批量歌曲详情：歌名/歌手/专辑/时长/别名/热度 |
| `netease lyric <id>` | 歌词 LRC 原文 + 翻译歌词 `tlyric`、逐字歌词 `klyric`（有则给） |
| `netease playlist <id> [--limit N]` | 歌单信息 + 曲目列表（默认 20 首） |
| `netease artist <id> [--with albums\|intro]` | 歌手资料 + 热门 50 首；可选附专辑列表（30 张）或歌手介绍全文 |
| `netease album <id>` | 专辑信息 + 全部曲目 |
| `netease toplist` | 官方榜单目录（60+ 榜单 + 歌手榜信息） |
| `netease recommend [--limit N]` | 匿名推荐歌单 |
| `netease doctor` / `netease commands` | 通道健康检查（cloudsearch + lyric 双探针）/ 机器可读能力清单 |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
# 统一仓 agent-plugins 的子目录
cd agent-plugins/netease
./netease search "周杰伦" --type artist   # 仅需 Python 3.8+，无第三方依赖
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`netease`、`netease.py`）
放进 Agent 的 skills 目录即可。

## 边界（如实）

- **单曲搜索排序与官方客户端不一致**：匿名态下版权曲可能沉底——
  例如搜「周杰伦 晴天」，原版《晴天》不置顶，前排是翻唱版本；
  songCount 等计数真实。歌手、歌单、专辑搜索精准，无此问题。
  找某位歌手的某首歌，建议先 `search --type artist` 拿歌手 id，
  再看 `artist` 的热门歌曲或专辑曲目，比单曲搜索可靠。
- **只有元数据与歌词**：没有播放地址、不下载；登录类功能
  （我的歌单/收藏/每日推荐歌曲等账号面）未做。
- 本接口面是服务端保留的**明文兼容面，非官方公开承诺**，
  随时可能收紧；失效时 `doctor` 会如实报错、命令返回业务 code，
  插件不编造数据。请求已内置 0.45 秒节流，保持低频使用。
- 歌单详情接口内嵌的曲目只给前 10 首，插件会按 `trackIds`
  自动批量补全到 `--limit` 指定的数量；补全走歌曲详情接口，
  大歌单拉全量会产生多次请求，注意节流耗时。
- 歌词为网易云用户/官方维护的 LRC：个别歌曲只有「暂无歌词」
  占位文本，翻译与逐字歌词并非每首都有，缺失时字段为 null。
- 与 `music` 插件分工：netease 管网易云曲库（华语覆盖全、带歌词），
  music 管 iTunes/MusicBrainz（国际曲库元数据、ISRC、30 秒试听）。
