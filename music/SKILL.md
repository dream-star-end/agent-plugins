---
name: music-cli
description: 音乐元数据检索 CLI：当用户问某首歌/专辑/歌手的信息、想找歌听个试听片段、查歌曲发行版本或 ISRC 时，用本插件的 music 命令查 iTunes 与 MusicBrainz（免密钥）。含歌曲/专辑/歌手搜索、按 id 查详情、音乐百科检索；只给元数据与 30 秒试听，不提供完整播放/下载。
---

# 音乐 CLI（Agent 插件）

可执行文件：本插件目录下的 `music`（SKILL.md 同级，纯 Python 3 标准库，零依赖）。
数据源 iTunes Search API + MusicBrainz（均免密钥）。完整说明见同目录 `README.md`。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 搜歌：`music search "Jay Chou" --limit 10`（歌名、歌手、专辑、时长、发行日期、价格、30 秒试听 preview_url、600px 封面）
- 搜专辑/歌手：`music search 周杰伦 --entity album`、`music search "Taylor Swift" --entity artist`
- 查详情：`music lookup 123456789`（track id）；`music lookup <collectionId> --entity album` 返回专辑曲目
- 百科检索：`music mb 晴天 --kind recording`（录音：时长/首发/ISRC/版本）、`music mb 周杰伦 --kind artist`

全局选项（任意位置）：`--table` 表格、`--compact` 单行 JSON、`--fields a,b` 字段裁剪。
自检：`music doctor`；能力清单：`music commands`。

## 注意

- **iTunes 默认查美区（US）**：大陆区（CN）商店的音乐搜索实测恒返回 0 条，查不到先确认 country 是 US/HK，不要据此断言「没有这首歌」。
- preview_url 只是 30 秒试听片段，不要说成完整歌曲；本插件不提供完整播放地址、不下载音乐。
- MusicBrainz 的 score 是相关性分，中文检索排序一般；引用具体条目前先看 score 与版本信息，不要把第一条默认当目标。
- 网易云/QQ 音乐的非官方接口经实测不可用（加密响应/接口下线），本插件不接入，不要尝试绕过。
