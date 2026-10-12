# Changelog

## 1.4.0（2026-10-12）

- 新增 `ths rt`：实时五档命令。新增常驻 sidecar（`sidecar/`，.NET 8 组件，
  源码 + `build.sh`），宿主加载同花顺 Linux 客户端 2.9.1.0 的
  `Hevo.Api.Quotes` 程序集，借其 QuoteV2/V3 DataCenter 通道取完整买卖
  五档（沪 USHA / 深 USZA / 北交所 USTM，映射以 `Market.ParseFromOldID`
  在真程序集上求值实证）；经 Unix socket IPC 对 `ths.py` 提供
  realtime/status/shutdown，`ths rt` 未运行时自动拉起，
  `ths rt status|stop` 管理；会话约 24h 由 sidecar 自动 re-verify 保活。
  实测（盘后快照）：600519 五档与 2b 宿主实测及 Web 网关参考值逐值一致，
  000977、920185 均取得完整五档。`doctor` 增加非关键项 `sidecar_realtime`。
- 边界不变：十档/逐笔为 Level-2 付费权益（IsLevel2=False 的账号拿不到）；
  sidecar 强绑定客户端 2.9.1.0、需 other_tcp 放行、与真客户端同账号互踢。

## 1.3.0（2026-10-12）

面向 AI agent 使用的系统性优化：

- 新增 `indicators`（MA/MACD/RSI/KDJ/BOLL 本地计算）、`doctor`（通道健康检查）、
  `commands`（机器可读能力清单）、`events`（F10 公司大事·近期重要事件）
- K 线标定为**前复权**（比亚迪送转除权日验证），输出标注 `adjust=forward`
- `kline`/`intraday`/`indicators` 支持板块目标（板块名/881xxx/885xxx 代码/bk_ 前缀），
  `quote` 支持板块代码与指数代码（1A0001）直查
- 北交所支持：920xxx 代码行情/F10 均可查（网关 hs_ 前缀）
- `f10 --deep` 核心指标补同比 `yoy_pct`，新增 `--all` 全量科目
- 输出瘦身：全局 `--compact`（单行 JSON）、`--fields`（字段裁剪）
- 错误带 `code` 字段（INVALID_CODE/NOT_FOUND/UPSTREAM/NETWORK/RATE_LIMIT 等）
- 短期文件缓存（行情 20s、K 线 2–30min、财报 6h；`THS_NO_CACHE=1` 禁用）
- GET 请求对 502/503/网络错误自动重试（POST 不重试）
- `watchlist list`/`screen` 补全改并发；`watchlist push` 实测通过
  并修复指数代码导致的中断

## 1.0.0（2026-10-12）

首个公开版本：quote/kline/intraday/search/screen/news/f10/rank/lhb/sector/
watchlist/login（短信登录 + 云自选同步），逆向自同花顺 Linux 客户端 Web 接口。
