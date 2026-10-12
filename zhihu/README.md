# zhihu-plugin · 知乎 Agent 插件

给 AI Agent 用的知乎工具包：**零依赖 CLI + Agent Skill**。

| 命令 | 说明 |
|---|---|
| `zhihu login set <Cookie串或z_c0值>` | 保存登录 cookie 到 ~/.zhihu_auth.json（0600） |
| `zhihu login status / logout` | 登录状态校验 / 清除凭据 |
| `zhihu me` | 我的资料（昵称/关注/回答/文章/获赞） |
| `zhihu search <关键词>` | 综合搜索（问题/回答/文章） |
| `zhihu question <ID\|链接> [--answers]` | 问题标题/回答数（取自回答接口），可附高赞回答 |
| `zhihu user <url_token>` | 用户资料 |
| `zhihu fav` | 我的收藏夹列表 |
| `zhihu doctor` / `zhihu commands` | 健康检查 / 能力清单 |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 登录设计（面向 agent 接入）

知乎二维码生成接口由商业设备指纹 SDK（du_web_sdk）守门：请求必须
携带 SDK 在真实浏览器里签发的 BrowserID，服务端会校验签发记录，
纯 API 伪造过不了（已实测 xsrf/udid/d_c0 多种组合，均 400）。
因此本插件的登录分工是 **CLI 管流程与凭据、宿主浏览器只负责出码**：

供 agent 执行的标准引导流程（用户只做扫码一步）：
1. 用宿主浏览器打开 https://www.zhihu.com/signin ，停在扫码登录页；
2. 用户用知乎 App 扫码并确认，浏览器跳到已登录首页；
3. agent 读取浏览器中 zhihu.com 域的 cookie（需含 z_c0）；
4. 执行 `zhihu login set -`（cookie 从 stdin 传入）或
   `zhihu login set '<Cookie 串>'` 落盘到 ~/.zhihu_auth.json（0600）；
5. `zhihu login status` 验证。之后所有 agent 共用该凭据调内容命令，
   凭据失效时重走 1–5。

不要让用户自己去开发者工具里翻 cookie——那是 agent 的活。

## 状态说明

内容解析已于 2026-10-12 用真实登录态响应逐字段验证并修正：裸
/questions 接口官方返回 10003 已弃用，question 改走回答接口；
members 系列接口必须带 include 才给计数；favlists 不提供计数。
CLI 端到端（cookie 传输）仍待 z_c0 落盘后复验。登录存储、状态校验
与各内容命令已按知乎 v4 API 实现；内容解析
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
