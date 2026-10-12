---
name: pubmed-cli
description: PubMed 生物医学文献检索 CLI：当用户问医学/生物/疾病/药物/临床研究方面的文献、找某种病或疗法的研究证据、查某篇医学论文的摘要时，用本插件的 pubmed 命令检索 NCBI PubMed（免密钥）。含关键词检索与按 PMID 取摘要全文。
---

# PubMed CLI（Agent 插件）

可执行文件：~/workspace/agent-plugins/pubmed/pubmed（纯 Python 3 标准库，零依赖）。
数据源：NCBI E-utilities（PubMed 官方接口）。完整说明见同目录 `README.md`。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 文献检索：`pubmed search "CRISPR gene editing" --limit 10`（相关度排序；返回命中总数与 PMID/标题/期刊/日期/作者/DOI）
- 检索式可用 PubMed 语法：`"diabetes mellitus"[Title]`、`Wang J[Author]`、`2024[Year]`，可 AND/OR 组合
- 文献详情：`pubmed paper 35251086`（标题、摘要全文、作者、期刊、日期、DOI、MeSH 关键词）

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。自检 `pubmed doctor`；清单 `pubmed commands`。

## 注意

- 摘要是英文原文；给用户汇报时翻译要点并保留英文标题与 PMID/DOI。
- 仅生物医学库；其他学科文献不在 PubMed 范围内，不要硬凑。
- 部分老文献无摘要（abstract 为 null），如实说明，不要编造。
- 无密钥限速约 3 次/秒，工具已自动节流；不要高频批量调用。
