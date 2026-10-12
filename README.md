# agent-plugins · AI Agent 插件家族

给 AI Agent 用的工具插件集：**8 个零依赖 CLI + 配套 Skill**，覆盖行情、
天气、基金、热搜、汇率、论文、地图、视频。每个插件独立可用，统一规格：

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
| **hot** 热搜 | 知乎/百度/头条/B站/微博热榜聚合 | `list` | [hot/README.md](hot/README.md) |
| **fx** 汇率 | 法币汇率换算 + 加密货币行情 | `rate` `currencies` `crypto` | [fx/README.md](fx/README.md) |
| **arxiv** 论文 | arXiv 检索/分类最新/按 ID 取论文 | `search` `recent` `paper` `categories` | [arxiv/README.md](arxiv/README.md) |
| **map** 地图 | 地理编码/路线/周边 POI（OpenStreetMap） | `geocode` `reverse` `route` `poi` | [map/README.md](map/README.md) |
| **bili** B站 | 视频搜索/详情/排行/热门/UP主/评论 | `search` `video` `rank` `popular` `up` `comments` | [bili/README.md](bili/README.md) |

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
- bili：字幕/弹幕需登录态，未纳入；fx：法币为日频参考汇率（非实时牌价）。

## License

MIT
