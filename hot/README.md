# hot-plugin · 全网热搜聚合 Agent 插件

给 AI Agent 用的热搜工具包：**零依赖 CLI + Agent Skill**，聚合五大平台
热榜（均为公开接口，无需密钥），单源失败自动隔离。

| 源 | 内容 | 热度字段 |
|---|---|---|
| `zhihu` 知乎热榜 | 问题标题 | 热度文本（如「908 万热度」） |
| `baidu` 百度热搜 | 热搜词 | 该接口不提供数值 |
| `toutiao` 头条热榜 | 话题标题 | 热度值 |
| `bili` B站热门 | 热门视频（标题/UP主） | 播放量 |
| `weibo` 微博热搜 | 热搜词（热/沸/新标签） | 搜索热度 |

微博登录（可选，提升稳定性）：`hot login qr` 生成官方二维码图 → 微博 App 扫码 → `hot login poll` 落盘凭据（~/.weibo_auth.json）；登录后微博源优先走登录态，失败自动回落访客流程。`hot login status/logout` 查看与退出。

```bash
hot list                       # 全部源聚合（每源带 ok 状态）
hot list --source weibo        # 单个源
hot doctor                     # 逐源健康检查
```

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
git clone https://github.com/dream-star-end/hot-plugin.git
cd hot-plugin
./hot list --limit 10     # 仅需 Python 3.8+，无第三方依赖
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`hot`、`hot.py`）放进
Agent 的 skills 目录即可。

## 边界

- 各源热度口径不同，不可跨源直接比较或合并排名。
- 微博源需自动走 passport 访客流程拿 cookie（缓存在 `~/.hot_cache/`），
  是五源中最不稳定的；失败时聚合结果中单独标注，不影响其他源。
- B站官方热搜词接口已下线（404），B站源为热门视频榜。

## License

MIT
