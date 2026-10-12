---
name: zhihu-cli
description: 知乎查询 CLI：当用户问知乎上的问题、回答、某用户的资料、自己的知乎收藏，或要在知乎搜内容时，用本插件的 zhihu 命令。登录为 cookie 方式（知乎扫码接口有签名墙）：用户从浏览器复制 z_c0 后用 login set 存入本机。
---

# 知乎 CLI（Agent 插件）

可执行文件：本插件目录下的 `zhihu`（SKILL.md 同级，纯 Python 3 标准库，零依赖）。
完整说明见同目录 `README.md`。热榜在 hot 插件里，本插件管内容与账号。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 登录：`zhihu login set`（凭据存本机 ~/.zhihu_auth.json）；`zhihu login status` 校验；未登录时内容命令会报 AUTH 错误。**登录引导由 agent 执行**（见下节），不要让用户自己翻开发者工具找 cookie
- 我的：`zhihu me`、`zhihu fav`（收藏夹列表）
- 搜索：`zhihu search "大模型" --limit 10`
- 问题：`zhihu question 2092747969921602735 --answers`（详情 + 高赞回答摘要）
- 用户：`zhihu user <url_token>`（知乎个人主页 URL 里 /people/ 后面那串）

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。自检 `zhihu doctor`；清单 `zhihu commands`。

## 登录引导流程（agent 执行，用户只扫码）

知乎二维码生成接口被商业指纹 SDK（du_web_sdk）守门，纯 API 扫码
做不了。需要登录时按此流程（与 README 一致）：
1. 用你的浏览器工具打开 https://www.zhihu.com/signin 停在扫码页；
2. 请用户用知乎 App 扫码确认（这是用户唯一要做的事）；
3. 登录成功后读取浏览器中 zhihu.com 域 cookie（须含 z_c0）；
4. `zhihu login set -` 从 stdin 传入 cookie 串落盘；
5. `zhihu login status` 验证后继续用内容命令。

## 注意

- 不要向用户承诺「纯 API 扫码登录知乎」，也不要让用户手动复制 cookie。
- z_c0 是登录凭据，只存本机、不要外传或写进任何输出/日志。
- 内容解析待真实凭据实测校准；若某命令返回结构异常，如实报告并保留原始错误。
