# arxiv-plugin · 学术论文 Agent 插件

给 AI Agent 用的论文检索工具包：**零依赖 CLI + Agent Skill**，
数据源 arXiv 官方 API（免费、无需密钥）。

| 命令 | 说明 |
|---|---|
| `arxiv search <关键词> [--author/--title/--category/--sort/--limit]` | 论文检索（相关度或提交日期排序） |
| `arxiv recent <分类> [--limit N]` | 某分类最新提交（cs.AI/cs.CL/cs.CV/cs.LG 等） |
| `arxiv paper <ID>` | 按 arXiv ID 取单篇：标题/摘要/作者/分类/DOI/PDF 链接 |
| `arxiv categories` | 常用分类速查 |
| `arxiv doctor` / `arxiv commands` | 通道健康检查 / 机器可读能力清单 |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
git clone https://github.com/dream-star-end/arxiv-plugin.git
cd arxiv-plugin
./arxiv recent cs.CL --limit 5    # 仅需 Python 3.8+
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`arxiv`、`arxiv.py`）放进
Agent 的 skills 目录即可。

## 边界

- 仅覆盖 arXiv 收录的预印本（未经同行评审）；不含付费期刊全文与引用数数据。

## License

MIT
