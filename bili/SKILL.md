---
name: bili-cli
description: 哔哩哔哩查询 CLI：当用户问 B站视频、UP主、排行榜、热门、某视频的评论，或要在 B站搜视频时，用本插件的 bili 命令（公开接口，免登录）。含视频搜索、视频详情、全站排行、热门、UP主信息、评论。
---

# B站 CLI（Agent 插件）

可执行文件：本插件目录下的 `bili`（SKILL.md 同级，纯 Python 3 标准库，零依赖）。
数据源：B站公开 Web 接口（无需登录）。完整说明见同目录 `README.md`。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 搜视频：`bili search "AI 日报" --limit 10`（`--order click` 按播放、`pubdate` 按最新）
- 视频详情：`bili video BV1xx411c7mD`（标题、UP主、播放/弹幕/评论/收藏/投币/分享/点赞、分P、简介、发布时间）
- 排行榜：`bili rank --limit 20`（全站；`--rid` 分区号，0=全站）
- 热门：`bili popular --limit 20`
- UP主：`bili up 3493260618106936`（mid 是数字用户 ID；粉丝数、获赞数、稿件数、签名）
- 评论：`bili comments BV1xx411c7mD --sort hot --limit 10`（hot 热门 / time 最新）
- 登录（全 CLI 化）：`bili login qr` 生成二维码 PNG → 用户 B站 App 扫码 → `bili login poll` 完成登录（凭据存本机 ~/.bili_auth.json）；`bili login status/logout` 查看与退出
- 字幕：`bili subtitle BV1xx411c7mD`（全文 + 分段，一般需先登录才有 AI 字幕）
- 弹幕：`bili danmaku BV1xx411c7mD --limit 500`（时间轴 + 内容）
- 我的：`bili me`、`bili fav [--folder <id>]`（收藏夹）、`bili history`（观看历史），均需登录

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。自检 `bili doctor`；清单 `bili commands`。

## 注意

- 免登录可达范围：搜索/详情/排行/热门/UP主/评论/弹幕。**字幕（尤其 AI 字幕）与收藏夹/历史需要登录态**：未登录时先引导用户走 `bili login qr` 扫码流程，不要编造字幕内容。
- 视频详情走视频页解析（view 接口对机房 IP 常返回 412）；播放量等数据为抓取时刻快照。
- 搜索结果标题已去除高亮标签；`play` 是累计播放量。
