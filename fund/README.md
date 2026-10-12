# fund-plugin · 公募基金 Agent 插件

给 AI Agent 用的基金工具包：**零依赖 CLI + Agent Skill**，数据源为
天天基金/东方财富公开接口（无需密钥）。

| 命令 | 说明 |
|---|---|
| `fund search <关键词>` | 按名称/拼音/代码搜基金（全量约 2.8 万只，索引本地缓存 7 天） |
| `fund nav <代码> [--limit N]` | 历史净值：单位/累计净值、日涨跌幅、申购赎回状态、分红 |
| `fund info <代码>` | 基金资料：现行/原费率、最低申购、近 1 月/3 月/6 月/1 年收益、资产配置、前十大持仓代码、最新净值 |
| `fund holdings <代码>` | 最新季报持仓明细：股票、占净值比例、持股数（万股）、市值（万元） |
| `fund rank [--type ...] [--by ...]` | 收益排行（类型：全部/股票/混合/债券/指数/QDII/FOF；周期：日/周/月/季/半年/1-3 年/今年来） |
| `fund doctor` / `fund commands` | 通道健康检查 / 机器可读能力清单 |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
git clone https://github.com/dream-star-end/fund-plugin.git
cd fund-plugin
./fund search 沪深300     # 仅需 Python 3.8+，无第三方依赖
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`fund`、`fund.py`）放进
Agent 的 skills 目录即可。

## 边界

- **无盘中估值**：老牌估值接口 fundgz 已被东方财富下线，本工具只提供
  日终官方净值，不提供也不编造盘中估算净值。
- 持仓为季报披露数据，滞后 1–3 个月。
- 排行口径为天天基金公开排行；个别基金因大额赎回等会出现净值异动极端值。

## License

MIT
