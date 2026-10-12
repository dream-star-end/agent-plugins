# rss — RSS/Atom 订阅阅读 CLI

给 AI agent / 脚本用的通用 feed 读取工具：给一个 RSS/Atom 地址，
抓取解析成统一 JSON 字段，不用每个站点单独适配。

| 命令 | 说明 |
|---|---|
| `rss read <feed URL> [--limit N]` | 抓取并解析 RSS 2.0 / RSS 1.0(RDF) / Atom，输出源标题、源链接与条目（title/link/published/author/summary） |
| `rss feeds` | 内置常用源速查表（仅收录实测可达且可解析的源） |
| `rss doctor` | 逐个检查内置源可达性 + 示例源解析 |
| `rss commands` | 机器可读能力清单 |

全局选项：`--table` 表格输出、`--compact` 单行 JSON、`--fields a,b` 字段裁剪。
错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

## 输出约定

- `published` 尽量归一化为 `YYYY-MM-DD HH:MM`（兼容 RFC822 与 ISO8601），
  解析失败时保留原文。
- `summary` 已去 HTML 标签并截断到 200 字；RSS 取 description（缺失时用
  content:encoded），Atom 取 summary（缺失时用 content）。
- 作者：RSS 优先 dc:creator，其次 author；Atom 取 author/name。

## 安装

```sh
chmod +x rss rss.py
./rss feeds
```

纯 Python 3 标准库，零依赖。

## 边界（如实说明）

- 只做标准 XML 解析：源返回非法 XML（如标签不闭合）会直接报错。
  例如机器之心 `https://www.jiqizhixin.com/rss`（2026-10-12 实测）
  返回的 XML 不合法，故未收入内置源表。
- 内置源可达性随源站与网络环境变化（个别源可能需要代理或偶发限流），
  `rss doctor` 的单项结果即当时实测状态。
- 不做订阅管理、已读状态与全文抓取；只读 feed 本身。

## License

MIT
