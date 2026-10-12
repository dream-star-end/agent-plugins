# bili-plugin · 哔哩哔哩 Agent 插件

给 AI Agent 用的 B站工具包：**零依赖 CLI + Agent Skill**，
B站公开 Web 接口，无需登录。

| 命令 | 说明 |
|---|---|
| `bili search <关键词> [--limit N] [--order ...]` | 视频搜索（WBI 签名自动处理，密钥日缓存） |
| `bili video <BV号\|av号\|链接>` | 视频详情：标题/UP主/七项数据统计/分P/简介/发布时间 |
| `bili rank [--rid 0] [--limit N]` | 全站/分区排行榜 |
| `bili popular [--limit N]` | 热门视频 |
| `bili up <mid>` | UP主信息：粉丝/关注/获赞/稿件数/签名/等级 |
| `bili comments <BV号> [--sort hot\|time]` | 热门或最新评论（含点赞数） |
| `bili login qr/poll/status/logout` | 扫码登录（全 CLI 化：生成二维码→轮询→凭据存 ~/.bili_auth.json） |
| `bili subtitle <BV号>` | 视频字幕全文（含 AI 字幕，需登录） |
| `bili danmaku <BV号>` | 弹幕列表（时间轴/内容/发送时间） |
| `bili me` / `bili fav` / `bili history` | 我的账号 / 收藏夹 / 观看历史（需登录） |
| `bili like/coin/favadd/favdel/follow` | 写操作：点赞/投币/收藏/取消收藏/关注取关（需登录；点赞·收藏·关注已实测往返，投币不可撤销未做真投测试） |
| `bili comment/commentdel/senddm` | 写操作：发评论/删自己的评论/发弹幕（需登录；评论已实测发+删，弹幕已实测发送成功；弹幕不可撤回） |
| `bili doctor` / `bili commands` | 通道健康检查 / 机器可读能力清单 |

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。
错误为 stderr 的 `{"error": ..., "code": ...}` + 退出码 1。

## 安装

```bash
git clone https://github.com/dream-star-end/bili-plugin.git
cd bili-plugin
./bili search "AI 日报"     # 仅需 Python 3.8+
```

作为 Agent Skill：把本目录（含 `SKILL.md`、`bili`、`bili.py`）放进
Agent 的 skills 目录即可。

## 实现要点与边界

- 搜索走 WBI 签名接口：密钥从 nav 接口获取并按日缓存于 `~/.bili_cache/`，
  buvid 指纹经 spi 接口自动获取。
- 视频详情的主通道是视频页 `__INITIAL_STATE__` 解析：view 接口对
  不少机房 IP 段返回 412，页面解析更稳，接口作为兜底。
- 登录为二维码流程（`bili login qr` 生成 PNG 二维码 → B站 App 扫码 → `bili login poll` 落盘凭据），凭据仅存本机 ~/.bili_auth.json（0600），二维码渲染用内置的 qrcodegen（MIT 单文件）。不含视频下载功能。

## License

MIT
