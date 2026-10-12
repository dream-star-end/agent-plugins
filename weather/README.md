# weather-plugin · 天气 Agent 插件

给 AI Agent 用的天气工具包：**零依赖 CLI + Agent Skill**，数据源
[Open-Meteo](https://open-meteo.com/)（免费、无需 API 密钥）。

| 命令 | 说明 |
|---|---|
| `weather now <城市>` | 当前天气（温度/体感/湿度/风/气压）+ 今日概览 |
| `weather forecast <城市> [--days 1-16]` | 逐日预报：天气、高低温、降水量与概率、最大风速、紫外线、日出日落 |
| `weather air <城市>` | 空气质量：AQI（美标/欧标）、PM2.5、PM10、CO/NO₂/O₃（CAMS 模型估算，非实测） |
| `weather search <城市>` | 城市消歧：候选地点、行政区划、经纬度 |
| `weather doctor` / `weather commands` | 通道健康检查 / 机器可读能力清单 |

城市可用中文名、英文名或 `lat,lon` 坐标。全局选项（任意位置）：
`--table`、`--compact`、`--fields a,b`。错误为 stderr 的
`{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
git clone https://github.com/dream-star-end/weather-plugin.git
cd weather-plugin
./weather now 北京        # 仅需 Python 3.8+，无第三方依赖
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`weather`、`weather.py`）
放进 Agent 的 skills 目录即可。

## 边界

- 无中国天气预警（预警信号）数据；AQI 为模型估算而非监测站实测。
- 预报为数值模式结果，短时临近预报存在误差。

## License

MIT
