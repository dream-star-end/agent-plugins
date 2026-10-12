# podcast-plugin · 播客 Agent 插件

给 AI Agent 用的播客工具包：**零依赖 CLI + Agent Skill**。数据源
[iTunes Search API](https://itunes.apple.com/search)（免费、无需密钥）
+ 节目自身的 RSS feed。

| 命令 | 说明 |
|---|---|
| `podcast search <关键词> [--limit N] [--country CN\|US]` | 按关键词搜播客：节目名/作者/单集总数/类型/feed 地址（iTunes 索引，按国家分区） |
| `podcast episodes <collectionId\|feedUrl> [--limit N]` | 单集列表：标题、发布时间、时长、音频直链、文件大小、摘要（解析节目 RSS） |
| `podcast doctor` / `podcast commands` | 通道健康检查 / 机器可读能力清单 |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。错误为
stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
git clone https://github.com/dream-star-end/agent-plugins.git
cd agent-plugins/podcast
./podcast search 科技        # 仅需 Python 3.8+，无第三方依赖
./podcast episodes 1494812579 --limit 5
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`podcast`、`podcast.py`）
放进 Agent 的 skills 目录即可。

## 边界

- 搜索范围是 **iTunes（Apple Podcasts）索引**，不是全网播客：小宇宙等
  平台独占、未提交 iTunes 的节目搜不到；索引按 `--country` 分区，
  CN 区没有的节目可试 `--country US`。
- 单集列表来自节目 RSS：部分 feed 已失效、需特定网络环境或体积很大
  （数 MB 级）时抓取较慢，失败会如实报错（UPSTREAM/NETWORK）。
- 仅支持 RSS 2.0 feed；Atom feed 暂不支持（会明确报错）。
- 时长取 RSS 的 `itunes:duration`，同时给出原始值与换算秒数；
  个别节目该字段缺失或不规范时为 null。

## License

MIT
