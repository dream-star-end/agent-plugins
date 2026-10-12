---
name: podcast-cli
description: 播客搜索与单集列表 CLI：当用户问有什么播客、找某个主题/某人的播客节目、某播客最新一集讲了什么、要单集音频链接时，用本插件的 podcast 命令查 iTunes 索引并解析节目 RSS（免密钥）。含节目搜索、单集列表（标题/发布时间/时长/音频直链/摘要）。
---

# 播客 CLI（Agent 插件）

可执行文件：本插件目录下的 `podcast`（SKILL.md 同级，纯 Python 3 标准库，零依赖）。
数据源 iTunes Search API（免密钥）+ 节目 RSS。完整说明见同目录 `README.md`。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 搜节目：`podcast search 科技 --limit 10`（返回节目 id、作者、单集总数、类型、feed 地址；默认 CN 区索引，搜不到时加 `--country US` 再试）
- 单集列表：`podcast episodes 1494812579 --limit 5`（参数可为 search 给出的节目 id，也可直接给 RSS feed URL；返回标题、发布时间、时长、音频直链、摘要）

全局选项（任意位置）：`--table` 表格、`--compact` 单行 JSON、`--fields a,b` 字段裁剪。
自检：`podcast doctor`；能力清单：`podcast commands`。

## 注意

- 搜索范围只是 iTunes/Apple Podcasts 索引，分国家区：小宇宙独占节目、未上架
  iTunes 的节目搜不到，不要编造节目或单集信息。
- 单集来自节目 RSS 实时解析：feed 失效或抓不到时如实报错，不要用搜索结果
  的 trackCount 推测单集内容。
- 摘要是节目方自写的单集简介截断（约 200 字），引用时注明是简介而非逐字稿。
