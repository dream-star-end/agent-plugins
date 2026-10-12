# fx-plugin · 汇率与数字资产 Agent 插件

给 AI Agent 用的汇率工具包：**零依赖 CLI + Agent Skill**，公开接口免密钥。

| 命令 | 说明 |
|---|---|
| `fx rate <BASE> [--to CNY,EUR] [--amount N]` | 法币汇率（Frankfurter，欧洲央行日频参考汇率）+ 金额换算 |
| `fx currencies` | 支持的法币列表（约 30 种，含中文名） |
| `fx crypto BTC,ETH` | 加密货币行情（OKX 现货：现价/买卖一/24h 涨跌/高低/成交量） |
| `fx doctor` / `fx commands` | 通道健康检查 / 机器可读能力清单 |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
git clone https://github.com/dream-star-end/fx-plugin.git
cd fx-plugin
./fx rate USD --to CNY --amount 100   # 仅需 Python 3.8+
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`fx`、`fx.py`）放进
Agent 的 skills 目录即可。

## 边界

- 法币为日频参考汇率（非实时中间价、非银行牌价）；加密为 OKX 单所现货价
  （Binance 公开接口对部分地区返回 451，未接入）。

## License

MIT
