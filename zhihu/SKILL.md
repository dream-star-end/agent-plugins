---
name: zhihu-cli
description: 知乎查询 CLI：当用户问知乎上的问题、回答、某用户的资料、自己的知乎收藏，或要在知乎搜内容时，用本插件的 zhihu 命令。登录为 cookie 方式（知乎扫码接口有签名墙）：用户从浏览器复制 z_c0 后用 login set 存入本机。
---

# 知乎 CLI（Agent 插件）

可执行文件：本插件目录下的 `zhihu`（SKILL.md 同级，纯 Python 3 标准库，零依赖）。
完整说明见同目录 `README.md`。热榜在 hot 插件里，本插件管内容与账号。

## 用法

所有命令默认输出 JSON；错误时 stderr 输出 `{"error": ..., "code": ...}` 且退出码 1。

- 登录：`zhihu login set '<Cookie 串或 z_c0 值>'`（凭据存本机 ~/.zhihu_auth.json）；`zhihu login status` 校验；未登录时内容命令会报 AUTH 错误
- 我的：`zhihu me`、`zhihu fav`（收藏夹列表）
- 搜索：`zhihu search "大模型" --limit 10`
- 问题：`zhihu question 2092747969921602735 --answers`（详情 + 高赞回答摘要）
- 用户：`zhihu user <url_token>`（知乎个人主页 URL 里 /people/ 后面那串）

全局选项（任意位置）：`--table`、`--compact`、`--fields a,b`。自检 `zhihu doctor`；清单 `zhihu commands`。

## 注意

- 知乎扫码登录有设备指纹签名墙，本插件走 cookie 登录，不要向用户承诺扫码登录知乎。
- z_c0 是登录凭据，只存本机、不要外传或写进任何输出/日志。
- 内容解析待真实凭据实测校准；若某命令返回结构异常，如实报告并保留原始错误。
