# music-plugin · 音乐元数据 Agent 插件

给 AI Agent 用的音乐检索工具包：**零依赖 CLI + Agent Skill**，数据源
[iTunes Search API](https://itunes.apple.com)（Apple 官方）与
[MusicBrainz](https://musicbrainz.org)（开放音乐百科），均免密钥。

**定位是音乐元数据检索**：歌曲/专辑/歌手信息 + 30 秒试听链接 + 封面。
不是播放器——不提供完整歌曲播放地址、不下载音乐。

| 命令 | 说明 |
|---|---|
| `music search <关键词> [--entity song\|album\|artist] [--limit N] [--country US]` | iTunes 搜索：歌名/歌手/专辑、时长、发行日期、流派、价格（含币种）、30 秒试听 `preview_url`、600px 封面 |
| `music lookup <id> [--entity song\|album\|artist]` | 按 iTunes id 查详情；`--entity album` 传 collection id 返回专辑曲目列表，`artist` 传 artist id 返回其专辑 |
| `music mb <关键词> [--kind recording\|release\|artist] [--limit N]` | MusicBrainz 检索：录音（时长、首发日期、ISRC、所属发行）、发行版本（日期/国家/状态）、艺人（国家、类型、生卒/成立年份），每条带相关性 `score` |
| `music doctor` / `music commands` | 通道健康检查 / 机器可读能力清单 |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
# 统一仓 agent-plugins 的子目录
cd agent-plugins/music
./music search "Jay Chou" --limit 5   # 仅需 Python 3.8+，无第三方依赖
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`music`、`music.py`）
放进 Agent 的 skills 目录即可。

## 边界

- **iTunes 大陆区（CN）商店的音乐搜索实测恒返回 0 条**（本机出口下；
  同一接口的播客搜索却正常，原因不明），因此默认 `--country US`；
  HK 亦可。结果只覆盖 Apple 曲库收录的作品，区域曲库有差异。
- iTunes 的 `preview_url` 只是 30 秒试听片段，**不是完整歌曲**；
  价格为对应区商店标价，引用时带上 `currency` 与 `storefront`。
- MusicBrainz 是社区维护的百科数据：字段可能缺失，不同版本/翻唱
  容易混淆；其相关性排序对中文 query 一般，请结合 `score` 判断，
  不要把第一条默认当作目标。MB 官方限速 1 次/秒，插件已内置节流。
- iTunes 搜索的 `limit=1` 实测恒返回 0 条（接口怪癖），插件在
  limit<5 时自动按 5 取再截断；另外返回条数随 limit 变化，冷门词
  可能少于预期，属上游行为。
- 网易云音乐（搜索接口返回加密响应）、QQ 音乐（搜索接口已下线
  报 500）经实测均不可用，本插件不接入，也不要尝试绕过。

## License

MIT
