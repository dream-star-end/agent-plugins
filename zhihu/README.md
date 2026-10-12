# zhihu-plugin · 知乎 Agent 插件

给 AI Agent 用的知乎工具包：**零依赖 CLI + Agent Skill**。

| 命令 | 说明 |
|---|---|
| `zhihu login set <Cookie串或z_c0值>` | 保存登录 cookie 到 ~/.zhihu_auth.json（0600） |
| `zhihu login status / logout` | 登录状态校验 / 清除凭据 |
| `zhihu me` | 我的资料（昵称/关注/回答/文章/获赞） |
| `zhihu search <关键词>` | 综合搜索（问题/回答/文章） |
| `zhihu question <ID\|链接> [--answers]` | 问题详情，可附高赞回答 |
| `zhihu user <url_token>` | 用户资料 |
| `zhihu fav` | 我的收藏夹列表 |
| `zhihu doctor` / `zhihu commands` | 健康检查 / 能力清单 |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 为什么是 cookie 登录而不是扫码

知乎网页版二维码登录接口带设备指纹签名（d_c0 / x-zse-96），
无法像 B站、微博那样纯 API 扫码，本插件不逆向该签名。替代方案：
浏览器登录 zhihu.com 后，在开发者工具 → 应用 → Cookie 里复制
`z_c0` 的值（或整串 Cookie），执行 `zhihu login set '<粘贴>'` 即可。

## 状态说明

登录存储、状态校验与各内容命令已按知乎 v4 API 实现；内容解析
尚待真实 z_c0 凭据实测校准（doctor 会如实标注）。热榜功能在
hot 插件中（免登录），本插件不重复提供。

## 安装

```bash
git clone https://github.com/dream-star-end/agent-plugins.git
cd agent-plugins/zhihu
./zhihu login set '<你的 z_c0 或 Cookie 串>'
./zhihu me
```

## License

MIT
