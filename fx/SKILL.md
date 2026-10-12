---
name: fx-cli
description: 汇率与加密货币行情 CLI：当用户问汇率、换算外币、比特币/以太坊等加密货币价格时，用本插件的 fx 命令获取数据。法币为欧洲央行日频参考汇率（Frankfurter），加密行情来自 OKX 公开接口，均免密钥。
---

# 汇率/加密 CLI（Agent 插件）

可执行文件：本插件目录下的 `fx`（SKILL.md 同级，纯 Python 3 标准库，零依赖）。
完整说明见同目录 `README.md`。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 法币汇率：`fx rate USD --to CNY`（1 美元兑人民币，欧洲央行参考汇率）
- 金额换算：`fx rate USD --to CNY,EUR --amount 100`（converted 字段为换算结果）
- 支持法币：`fx currencies`
- 加密行情：`fx crypto BTC,ETH`（OKX 现货：现价、24h 涨跌幅、高低、成交量；也可写完整交易对 `BTC-USDT`）

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。自检 `fx doctor`；清单 `fx commands`。

## 注意

- 法币是**日频参考汇率**（欧洲央行每日公布，非实时交易中间价），输出带 `date`，引用时注明日期；周末/假日为最近工作日数据。
- 加密行情是 OKX 交易所现货价，不同交易所间有价差；引用时注明来源为 OKX。
- 不要把参考汇率当作银行结售汇价格（银行牌价含点差，本工具不提供）。
