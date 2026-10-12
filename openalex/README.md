# openalex-plugin · 学术全库检索 Agent 插件

给 AI Agent 用的学术检索工具包：**零依赖 CLI + Agent Skill**，
数据源 OpenAlex 官方 API（开放学术图谱，免费、无需密钥）。

| 命令 | 说明 |
|---|---|
| `openalex search <关键词> [--limit N]` | 论文搜索（标题/摘要/作者全文检索）：年份/类型/作者/期刊/引用数/DOI/开放获取状态 |
| `openalex work <OpenAlex ID\|DOI>` | 论文详情：摘要全文（由倒排索引还原）/参考文献数/被引数/主题/FWCI |
| `openalex author <姓名> [--limit N]` | 作者搜索：论文数/被引数/最近机构/ORCID |
| `openalex doctor` / `openalex commands` | 通道健康检查 / 机器可读能力清单 |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
# 统一仓 agent-plugins 的 openalex/ 子目录即本插件
cd agent-plugins/openalex
./openalex search "graph neural network" --limit 5    # 仅需 Python 3.8+
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`openalex`、`openalex.py`）
放进 Agent 的 skills 目录即可。

## 实现要点

- **摘要还原**：OpenAlex 出于版权原因只提供 `abstract_inverted_index`
  （`{词: [出现位置]}` 倒排索引），本工具按位置重排还原为可读摘要；
  出版商未提供摘要的论文该字段为 null（如部分 Nature 老论文）。
- 请求带 `mailto` 参数走 OpenAlex polite pool。
- `work` 接受三种引用：短 ID（`W2626778328`）、完整 URL
  （`https://openalex.org/W...`）、DOI（`10.1038/...` 或 `doi:10....`）。

## 边界

- 数据为开放学术图谱（汇聚 Crossref、MAG、出版社等），覆盖广但
  元数据质量参差：个别记录年份/版本可能与出版页不一致。
- **引用计数是 OpenAlex 自有图谱口径**，与 Google Scholar、
  Web of Science、Scopus 均不同，跨源不可直接比较。
- 只提供元数据与开放获取链接，不提供论文全文下载。
- 与 arxiv 插件分工：arxiv 管预印本的最新提交与原文摘要；
  openalex 管跨出版商的全库检索、引用计数与作者画像。

## License

MIT
