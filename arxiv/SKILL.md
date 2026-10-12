---
name: arxiv-cli
description: arXiv 论文检索 CLI：当用户问最新论文、某方向的研究、找某位作者的论文、或要某篇 arXiv 论文的摘要时，用本插件的 arxiv 命令检索 arXiv 官方 API（免密钥）。含关键词/作者/分类检索、分类最新、按 ID 取论文。
---

# arXiv CLI（Agent 插件）

可执行文件：本插件目录下的 `arxiv`（SKILL.md 同级，纯 Python 3 标准库，零依赖）。
数据源：arXiv 官方 API。完整说明见同目录 `README.md`。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 关键词检索：`arxiv search "diffusion policy" --limit 10`（默认相关度排序，`--sort date` 按提交日期）
- 限定条件：`--author "Yann LeCun"`、`--title "attention"`、`--category cs.CL`（可组合）
- 分类最新：`arxiv recent cs.AI --limit 10`（追踪某方向的新论文）
- 按 ID 取论文：`arxiv paper 1706.03762`（标题、摘要、作者、分类、PDF 链接）
- 分类速查：`arxiv categories`

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。自检 `arxiv doctor`；清单 `arxiv commands`。

## 注意

- 摘要是英文原文；给用户汇报时翻译要点并保留英文标题与 arXiv ID。
- `published` 是首次提交日期，`updated` 是最新版本日期；引用版本时用输出里的带 vN 后缀的 id。
- arXiv 是预印本平台（未经同行评审），引用结论时提醒这一点。
