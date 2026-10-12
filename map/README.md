# map-plugin · 地图出行 Agent 插件

给 AI Agent 用的地图工具包：**零依赖 CLI + Agent Skill**，数据源为
OpenStreetMap 生态公开服务（Nominatim/OSRM/Overpass，免密钥）。

| 命令 | 说明 |
|---|---|
| `map geocode <地名>` | 地名 → 经纬度 + 结构化地址（支持中文，多候选） |
| `map reverse <lat,lon>` | 经纬度 → 地址 |
| `map route <起点> <终点> [--mode driving\|walking\|cycling] [--steps]` | 路线规划：距离、时长、可选分步导航 |
| `map poi <类别> <地点> [--radius 米] [--limit N]` | 周边 POI（30 类）按距离排序，含名称/距离/地址/营业时间（有则给） |
| `map doctor` / `map commands` | 通道健康检查 / 机器可读能力清单 |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
git clone https://github.com/dream-star-end/map-plugin.git
cd map-plugin
./map route "北京故宫" "首都机场"    # 仅需 Python 3.8+
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`map`、`map.py`）放进
Agent 的 skills 目录即可。

## 边界

- OSM 社区数据在中国境内的 POI 密度与时效不如高德/百度；POI 仅查
  node 要素（面要素商户可能漏检）。
- Overpass 公共集群负载波动大，`poi` 已做多镜像多轮重试，仍可能
  偶发超时（耗时 10–30 秒属常见）；无实时路况，路线时长为模型估算。
- 坐标系 WGS-84，与国内地图 App（GCJ-02）坐标直接对比存在偏移。

## License

MIT。数据 © OpenStreetMap contributors（ODbL）。
