---
name: macro-cli
description: 世界银行宏观经济指标 CLI：当用户问某国 GDP/增速/CPI 通胀/失业率/人口/进出口等宏观数据、要跨国比较经济指标、或要查国家码与指标码时，用本插件的 macro 命令获取 World Bank 数据（免密钥，年度数据）。含时间序列、国家搜索、指标搜索与常用指标速查。
---

# macro — 世界银行宏观经济指标 CLI

可执行文件：`~/workspace/agent-plugins/macro/macro`（纯 Python 3 标准库，零依赖）

## 用法

- 时间序列：`macro data <国家码> <指标码> [--from 年] [--to 年]`
  例：`macro data CHN NY.GDP.MKTP.CD`（中国 GDP）、`macro data USA SL.UEM.TOTL.ZS --from 2010`
  输出含 latest（最新有值年份与数值）、series（逐年）、null_years（无数据年份）
- 搜国家码：`macro country <关键词>`（支持英文名，如 China、Japan、Germany）
- 搜指标：`macro indicator <关键词>`（如 inflation、unemployment、population）；
  给完整指标码（如 FP.CPI.TOTL.ZG）则精确查并返回官方说明
- 常用指标速查：`macro presets`（GDP/增速/人均 GDP/CPI/失业率/人口/城镇化/
  预期寿命/出口/进口/FDI/政府债务的代码表）
- 健康检查与能力清单：`macro doctor`、`macro commands`

## 注意

- 数据是**年度频率**且**滞后 1–2 年**、会被事后修订：引用最新值时带上年份
  （输出里的 latest.year），不要把空缺年份说成 0。
- 国家码用 ISO3（CHN/USA/JPN…），不确定先跑 `macro country` 查。
- 指标目录约 2.9 万条缓存在 ~/.macro_cache/indicators.json（30 天），
  首次 `indicator` 关键词搜索会慢几秒（拉全量目录），之后很快。
- 默认 JSON 输出；全局 `--table/--compact/--fields` 可调格式；错误带 code。
