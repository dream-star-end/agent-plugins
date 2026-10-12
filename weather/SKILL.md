---
name: weather-cli
description: 天气查询 CLI：当用户问天气、气温、降雨、空气质量、出行穿衣相关的天气问题时，用本插件的 weather 命令获取 Open-Meteo 数据（免密钥）。含当前天气、多日预报、空气质量、城市消歧。
---

# 天气 CLI（Agent 插件）

可执行文件：本插件目录下的 `weather`（SKILL.md 同级，纯 Python 3 标准库，零依赖）。
数据源 Open-Meteo（免费、无需 API 密钥）。完整说明见同目录 `README.md`。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 当前天气：`weather now 北京`（温度、体感、湿度、风、气压 + 今日高低温概览）
- 多日预报：`weather forecast 上海 --days 7`（逐日天气、降水概率、紫外线、日出日落）
- 空气质量：`weather air 北京`（AQI 分级、PM2.5/PM10；是 CAMS 模型估算值而非监测站实测，引用时要说明）
- 城市消歧：`weather search 苏州`（重名/多候选时先查经纬度再用 `lat,lon` 形式查询，如 `weather now 31.3,120.6`）

全局选项（任意位置）：`--table` 表格、`--compact` 单行 JSON、`--fields a,b` 字段裁剪。
自检：`weather doctor`；能力清单：`weather commands`。

## 注意

- 预报时区按城市所在时区返回，`current.time` 是当地时间。
- 中国天气预警（台风/暴雨预警信号）不在 Open-Meteo 覆盖内，不要编造预警信息。
- 数值是数值预报结果，临近降水等短时预报误差较大；做出行决策时给出不确定性提示。
