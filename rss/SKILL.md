---
name: rss-cli
description: RSS/Atom 订阅阅读 CLI：当用户要看某个博客/媒体/社区的最新文章、订阅源更新，或问"XX 网站最近发了什么"时，用本插件的 rss 命令抓取解析任意 RSS 2.0 / Atom feed（免密钥），并有内置常用源速查表（阮一峰/V2EX/少数派/量子位/Hacker News/BBC中文等）。
---

# rss CLI

可执行文件：`~/workspace/agent-plugins/rss/rss`（纯 Python 3 标准库，零依赖）

## 用法

- 读任意 feed：`rss read <feed URL> [--limit N]`，统一输出源标题、源链接、
  条目（title/link/published/author/summary）
- 内置源速查：`rss feeds`（9 个实测可达的常用源：阮一峰博客、V2EX、
  少数派、量子位、Hacker News、BBC 中文、GitHub 博客、Python 博客、NASA）
- 健康检查：`rss doctor`（内置源可达性 + 示例解析）
- 能力清单：`rss commands`

全局选项：`--table` / `--compact` / `--fields a,b`。

## 注意

- 日期已归一化为 `YYYY-MM-DD HH:MM`（失败保留原文）；summary 去 HTML 截断 200 字。
- 源返回非法 XML 会报错（如机器之心的 feed XML 不闭合，未收录）；
  个别源可能需代理或偶发限流，失败时看 doctor 单项结果，不要编造条目。
