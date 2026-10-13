# agent-plugins · AI Agent 插件家族

给 AI Agent 用的工具插件集：**17 个零依赖 CLI + 配套 Skill**，覆盖行情、
天气、基金、热搜、汇率、论文、地图、视频、知乎、宏观、全球行情、
生物医学、学术全库、播客、订阅、音乐、网易云。每个插件独立可用，统一规格：

- 纯 Python 3 标准库，**零第三方依赖**，克隆即跑
- 默认 **JSON 输出**；全局选项 `--table` / `--compact` / `--fields a,b`
- 错误统一为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1
- 每个插件自带 `doctor`（通道健康检查）与 `commands`（机器可读能力清单）

## 插件目录

| 插件 | 用途 | 主要命令 | 文档 |
|---|---|---|---|
| **ths** 同花顺行情 | A股行情/K线/选股/F10/板块/自选（支持短信登录） | `quote` `kline` `intraday` `search` `screen` `f10 --deep` `rank` `lhb` `sector` `watchlist` `indicators` `events` | [ths/README.md](ths/README.md) |
| **weather** 天气 | 当前天气/预报/空气质量（Open-Meteo） | `now` `forecast` `air` `search` | [weather/README.md](weather/README.md) |
| **fund** 基金 | 公募基金搜索/净值/资料/持仓/排行（天天基金） | `search` `nav` `info` `holdings` `rank` | [fund/README.md](fund/README.md) |
| **hot** 热搜 | 知乎/百度/头条/B站/微博热榜聚合（微博支持扫码登录） | `list` `login` | [hot/README.md](hot/README.md) |
| **fx** 汇率 | 法币汇率换算 + 加密货币行情 | `rate` `currencies` `crypto` | [fx/README.md](fx/README.md) |
| **arxiv** 论文 | arXiv 检索/分类最新/按 ID 取论文 | `search` `recent` `paper` `categories` | [arxiv/README.md](arxiv/README.md) |
| **map** 地图 | 地理编码/路线/周边 POI（OpenStreetMap） | `geocode` `reverse` `route` `poi` | [map/README.md](map/README.md) |
| **bili** B站 | 视频搜索/详情/排行/热门/UP主/评论 + 扫码登录/字幕/弹幕/收藏/历史 | `search` `video` `rank` `popular` `up` `comments` `login` `subtitle` `danmaku` `me` `fav` `history` | [bili/README.md](bili/README.md) |
| **zhihu** 知乎 | 搜索/问题/回答/用户/收藏（cookie 登录） | `login` `me` `search` `question` `user` `fav` | [zhihu/README.md](zhihu/README.md) |
| **stooq** 全球行情 | 美股/全球股票/指数/外汇/商品行情（Stooq，日线延迟） | `quote` `history` | [stooq/README.md](stooq/README.md) |
| **macro** 宏观 | 世界银行宏观经济指标（GDP/CPI/失业率等，年度） | `data` `country` `indicator` `presets` | [macro/README.md](macro/README.md) |
| **pubmed** 生物医学 | PubMed 文献检索/摘要（NCBI） | `search` `paper` | [pubmed/README.md](pubmed/README.md) |
| **openalex** 学术全库 | 跨出版商论文/作者检索（OpenAlex 开放学术图谱） | `search` `work` `author` | [openalex/README.md](openalex/README.md) |
| **podcast** 播客 | 播客搜索/单集列表/音频直链（iTunes 索引 + RSS） | `search` `episodes` | [podcast/README.md](podcast/README.md) |
| **rss** 订阅 | RSS/Atom 通用订阅阅读 | `read` `feeds` | [rss/README.md](rss/README.md) |
| **music** 音乐元数据 | 歌曲/专辑/歌手检索 + 30 秒试听（iTunes + MusicBrainz） | `search` `lookup` `mb` | [music/README.md](music/README.md) |
| **netease** 网易云 | 网易云音乐搜索/歌词/歌单/榜单（匿名接口面） | `search` `song` `lyric` `playlist` `toplist` | [netease/README.md](netease/README.md) |

## 快速开始

```bash
git clone https://github.com/dream-star-end/agent-plugins.git
cd agent-plugins

./weather/weather now 北京
./fund/fund search 沪深300
./hot/hot list --limit 10
./bili/bili search "AI 日报"
./ths/ths quote 600519        # ths 部分功能（登录/自选）需先 ./ths/ths login
```

## 作为 Agent Skill 使用

每个插件目录内含 `SKILL.md`。把需要的插件目录（含 `SKILL.md` 与
可执行文件）复制到你的 Agent 的 skills 目录下，Agent 即可按描述
自动发现并调用。

## 已知边界（详情见各插件 README）

- ths：客户端实时 GMS 协议、五档/逐笔、个股资金流金额未覆盖（私有协议/反爬/付费墙）。
- fund：无盘中估值（官方老接口已下线），只有日终官方净值。
- hot：各源热度口径不同不可跨源比较；微博源依赖访客流程，最不稳定。
- map：OSM 中国境内 POI 密度有限；Overpass 公共集群偶发慢。
- bili：字幕/收藏/历史需扫码登录（已 CLI 化）；fx：法币为日频参考汇率（非实时牌价）。

## License

MIT
