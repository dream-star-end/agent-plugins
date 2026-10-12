---
name: netease-cli
description: 网易云音乐元数据 CLI：当用户问网易云上的歌/歌手/专辑/歌单、要查歌词、看排行榜或推荐歌单时，用本插件的 netease 命令（匿名免登录）。含搜索（歌/歌手/专辑/歌单/歌词）、歌曲详情、歌词全文、歌单曲目、歌手热门与专辑；只有元数据与歌词，无播放地址。
---

# 网易云音乐 CLI（Agent 插件）

可执行文件：本插件目录下的 `netease`（SKILL.md 同级，纯 Python 3 标准库，零依赖）。
数据源：网易云音乐 `/api` 明文兼容面（匿名、无 Cookie）。完整说明见同目录 `README.md`。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 搜歌：`netease search "周杰伦 晴天" --limit 10`（注意单曲排序问题，见下方）
- 搜歌手/歌单/专辑：`netease search 周杰伦 --type artist`、`--type playlist`、`--type album`
- 按歌词搜歌：`netease search "塞纳河畔" --type lyric`（返回歌词含关键词的歌曲 + 命中歌词行）
- 歌曲详情：`netease song 19292984 2668397359`（可批量：歌名/歌手/专辑/时长/别名）
- 歌词：`netease lyric 19292984`（LRC 原文 + `tlyric` 翻译，缺失为 null）
- 歌单：`netease playlist 19723756 --limit 30`（歌单信息 + 曲目，自动补全详情）
- 歌手：`netease artist 6452`（资料 + 热门 50 首）；`--with albums` 附专辑、`--with intro` 附介绍
- 专辑：`netease album 274336916`（信息 + 全部曲目）
- 榜单/推荐：`netease toplist`、`netease recommend --limit 10`

全局选项（任意位置）：`--table` 表格、`--compact` 单行 JSON、`--fields a,b` 字段裁剪。
自检：`netease doctor`；能力清单：`netease commands`。

## 注意

- **单曲搜索（默认 type=song）排序与官方客户端不一致**：匿名态版权曲可能沉底，原版常不置顶（如搜「周杰伦 晴天」前排是翻唱）；计数真实。找某歌手的歌，优先 `search --type artist` 拿 id → `artist` 看热门/专辑曲目。歌手、歌单搜索精准。
- 只有元数据与歌词，**没有播放地址、不下载**；登录类功能（我的歌单/收藏/每日推荐）未做，不要尝试。
- 接口面是 2019 Linux 客户端的明文兼容面，非官方公开承诺；报错或查不到先跑 `netease doctor` 确认通道，不要编造结果。
