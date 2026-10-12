---
name: stooq-cli
description: 全球行情查询 CLI：当用户问美股/全球股票、标普道指等指数、外汇汇率走势、黄金原油等商品价格或历史日线时，用本插件的 stooq 命令获取 Stooq 数据（免密钥）。含多 symbol 报价、日线历史与区间涨跌；数据为日线/延迟行情，非实时 tick。
---

# Stooq 全球行情 CLI（Agent 插件）

可执行文件：本插件目录下的 `stooq`（SKILL.md 同级，纯 Python 3 标准库，零依赖）。
数据源 Stooq（免费、无需 API 密钥）。完整说明见同目录 `README.md`。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 报价：`stooq quote aapl.us ^spx eurusd xauusd`（多 symbol 一次查询；symbol 形如 `aapl.us` 美股、`^spx` 指数、`eurusd` 外汇、`xauusd` 黄金、`cl.f` 原油期货）
- 日线历史：`stooq history aapl.us --days 30`（最近 N 日 OHLCV + 区间涨跌）

全局选项（任意位置）：`--table` 表格、`--compact` 单行 JSON、`--fields a,b` 字段裁剪。
自检：`stooq doctor`；能力清单：`stooq commands`。

## 注意

- **数据是日线/延迟行情，不是实时价**：美股为收盘或延迟价，引用价格时必须说明数据日期（输出的 `date` 字段），不要说成「现价/实时价」。
- 涨跌口径：报价的 `change`/`change_pct` 是「收盘 − 当日开盘」，与按昨收算的涨跌幅不同，引用时注明口径。
- Stooq 对免费 CSV 按 IP 限流，报错 `NOT_FOUND`/`BLOCKED` 时先跑 `stooq doctor` 确认通道，不要编造价格。
- A 股/港股实时与深度数据不在本插件范围（用 ths 插件）；本插件补的是海外市场。
