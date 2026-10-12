---
name: openalex-cli
description: OpenAlex 学术检索 CLI：当用户问某个研究方向有哪些论文、某篇论文的摘要/引用数/参考文献、某位学者的论文数与被引量，或需要跨出版商查论文（不限于 arXiv）时，用本插件的 openalex 命令检索 OpenAlex 开放学术图谱（免密钥）。含论文搜索、按 OpenAlex ID/DOI 取详情（含还原摘要）、作者搜索。
---

# OpenAlex CLI（Agent 插件）

可执行文件：本插件目录下的 `openalex`（SKILL.md 同级，纯 Python 3 标准库，零依赖）。
数据源：OpenAlex 官方 API（开放学术图谱）。完整说明见同目录 `README.md`。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 论文搜索：`openalex search "transformer neural network" --limit 10`（标题/摘要/作者全文检索，返回年份/作者/期刊/引用数/DOI/开放获取）
- 论文详情：`openalex work W2626778328` 或 `openalex work doi:10.1038/nature14539` 或 `openalex work 10.1038/nature14539`（含还原后的摘要全文、参考文献数）
- 作者搜索：`openalex author "Yoshua Bengio" --limit 5`（论文数/被引数/机构/ORCID；同名作者需靠机构与论文数消歧）

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。自检 `openalex doctor`；清单 `openalex commands`。

## 注意

- 摘要由 OpenAlex 的倒排索引还原，内容忠实原文；出版商未提供摘要的论文 abstract 为 null，不要编造。
- 引用计数是 OpenAlex 图谱口径，与 Google Scholar 不一致，汇报时注明来源。
- 与 arxiv 插件分工：追最新预印本用 arxiv；查引用数、作者画像、跨出版商检索用 openalex。
