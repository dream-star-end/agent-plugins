# macro — 世界银行宏观经济指标 CLI

供 AI agent / 脚本调用的宏观经济数据工具。数据源为
[World Bank API v2](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation)
（免费、无需密钥），纯 Python 3 标准库、零依赖。

## 命令

| 命令 | 说明 |
|---|---|
| `macro data <国家码> <指标码> [--from 年] [--to 年]` | 某国某指标的年度时间序列（默认 2000–2026），含最新值、数据更新时间、空值年份标注 |
| `macro country <关键词>` | 按名称/代码搜国家：ISO3/ISO2 代码、首都、地区、收入等级 |
| `macro indicator <关键词\|指标码>` | 搜指标：给完整指标码走精确查（含官方说明摘要）；给词查本地全量目录（约 2.9 万条，缓存 30 天） |
| `macro presets` | 常用指标速查表（GDP、增速、人均 GDP、CPI、失业率、人口、城镇化、预期寿命、出口/进口占比、FDI、政府债务） |
| `macro doctor` | 通道健康检查（国家列表 / 指标数据 / 指标精确查） |
| `macro commands` | 机器可读能力清单 |

全局选项：`--table` 表格输出、`--compact` 单行 JSON、`--fields a,b` 字段裁剪。
错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

## 示例

```
macro country China
macro data CHN NY.GDP.MKTP.CD
macro data USA SL.UEM.TOTL.ZS --from 2010
macro indicator inflation
macro indicator FP.CPI.TOTL.ZG
```

## 数据边界

- **年度频率**：WDI 等数据库以年度为主，没有月度/季度序列；不要拿它当
  实时宏观数据用。
- **滞后与修订**：各国统计上报有延迟，最新年份通常滞后 1–2 年
  （如 2026 年查 GDP 多半只到 2024/2025 年），且历史值会被世行事后
  修订；输出里的 `source_last_updated` 是该库最近更新时间。
- **空值**：某些国家-年份没有数据，接口返回 null，本工具把有值年份放
  `series`、空值年份单列 `null_years`，不插值、不编造。
- **聚合体**：国家码除单个国家外也支持世行聚合代码（如 WLD 世界、
  EAS 东亚太平洋），用 `macro country` 或官方代码表确认。
- 指标关键词检索为本地全量目录的名称/代码包含匹配，官方 API 的
  `search` 参数实测不生效，本工具不依赖它。

## License

MIT
