# pubmed — 生物医学文献检索 CLI

供 AI agent / 脚本调用的 PubMed 文献检索工具：纯 Python 3 标准库、零依赖，
默认 JSON 输出。

## 数据源

NCBI E-utilities（美国国家生物技术信息中心官方接口，免费、无需密钥）：

- 检索 `esearch.fcgi`（db=pubmed，相关度排序）
- 摘要 `esummary.fcgi`（标题/期刊/日期/作者/DOI）
- 详情 `efetch.fcgi`（XML：摘要全文 + MeSH 关键词）

## 命令

| 命令 | 说明 |
|---|---|
| `pubmed search <关键词> [--limit N]` | 文献检索：命中总数 + PMID/标题/期刊/日期/作者/DOI |
| `pubmed paper <PMID>` | 文献详情：标题/摘要全文/作者/期刊/日期/DOI/MeSH 关键词 |
| `pubmed doctor` | 通道健康检查（esearch/esummary/efetch 三探针） |
| `pubmed commands` | 能力清单（机器可读） |

全局选项：`--table` 表格输出、`--compact` 单行 JSON、`--fields a,b` 字段裁剪。
错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

检索式支持 PubMed 语法，如 `"CRISPR"[Title] AND 2024[Year]`、作者 `Wang J[Author]` 等。

## 边界

- **仅生物医学库**：PubMed 收录生物医学与生命科学文献，其他学科请用 arxiv 等。
- **摘要为英文原文**：PubMed 摘要即英文原文输出，不做翻译；汇报时自行提炼。
- **速率限制**：无 API key 时 NCBI 限约 3 次/秒，本工具请求间自动节流
  （≥0.4s 间隔）并带 `tool=agent-cli` 标识；偶发 429 会自动重试。
- 部分老文献没有摘要全文（`abstract` 为 null），属数据源本身缺失。
- 期刊名、日期以 NCBI 记录为准；`pubdate` 可能为 `2024 Jan` 等部分日期格式。

## 安装

无需安装，Python 3 直接运行：

```sh
./pubmed search "CRISPR gene editing" --limit 5
```

## License

MIT
