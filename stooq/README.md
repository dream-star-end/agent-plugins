# stooq-plugin · 全球行情 Agent 插件

给 AI Agent 用的全球行情工具包：**零依赖 CLI + Agent Skill**，数据源
[Stooq](https://stooq.com/)（免费、无需 API 密钥）。

| 命令 | 说明 |
|---|---|
| `stooq quote <symbol...>` | 报价（可多 symbol）：日期/时间、OHLC、成交量、当日涨跌额/幅 |
| `stooq history <symbol> [--days N]` | 最近 N 日日线 OHLCV + 区间涨跌（默认 30 日） |
| `stooq doctor` / `stooq commands` | 通道健康检查 / 机器可读能力清单 |

symbol 写法（Stooq 约定）：

| 类别 | 示例 |
|---|---|
| 美股 / ETF | `aapl.us`、`spy.us` |
| 指数 | `^spx`（标普500）、`^dji`（道指）、`^ndx`（纳指100） |
| 外汇 | `eurusd`、`usdjpy`、`usdcnh` |
| 商品 | `xauusd`（黄金）、`xagusd`（白银）、`cl.f`（WTI 原油期货） |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
# 本插件位于 agent-plugins 统一仓的 stooq/ 子目录
cd agent-plugins/stooq
./stooq quote aapl.us ^spx    # 仅需 Python 3.8+，无第三方依赖
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`stooq`、`stooq.py`）
放进 Agent 的 skills 目录即可。

## 数据口径与边界

- **不是实时行情**：Stooq 免费数据多为日线/延迟数据，美股为收盘价或
  延迟价，`date`/`time` 字段是数据所属交易日与 Stooq 的时间戳；
  不要当作实时 tick 或盘中最新价引用。
- **涨跌口径**：报价 CSV 不提供昨收，`change`/`change_pct` 按
  「收盘价 − 当日开盘价」计算（当日振幅方向），与行情软件按昨收计算
  的涨跌幅不同，引用时须注明。history 的区间涨跌为窗口末日收盘
  相对首日收盘。
- **外汇/商品**为 Stooq 汇集的指示性报价，非交易所成交价。
- **限流**：Stooq 对免费 CSV 有按 IP 的频率/总量限制，超限时返回
  HTML 错误页或浏览器验证页，本工具会以 `NOT_FOUND`/`BLOCKED`/
  `UPSTREAM` 错误码如实报错，不会编造数据；高频调用请自行节流。
- 指数（如 ^spx）无成交量，`volume` 为 null。

## License

MIT
