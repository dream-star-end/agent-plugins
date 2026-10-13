# cc-api

给 Claude Code 套的一层壳：壳内打开一个**真实、有状态、可多轮**的 Claude Code 交互会话，
壳对外提供 **Anthropic Messages API 兼容**的 HTTP 接口（`POST /v1/messages`，支持流式 SSE）。

- 壳内会话 = 与 TUI 同源的 session（同一 transcript、可 `--resume` 接管、可多轮连续）
- 每次 API 调用 = 向该会话追加一轮（turn）；会话通过请求头 `x-cc-session` 做多会话隔离
- cc 的 **mods**（插件式 UI/交互扩展）通过 `--plugin-dir` 加载进壳内会话（配置 `mods_dirs`）
- 升级安全：只用公开 CLI flags（`-p/--verbose/--output-format stream-json/--session-id/--resume/--plugin-dir/...`），
  不补丁二进制、不写私有状态、不走 SDK-internal 的 stdio 控制协议；
  `cc-api doctor` 在每次 `claude update` 后校验协议兼容性

纯标准库，零依赖。

## 安装

```bash
# claude code 已装好即可（PATH 里有 claude）
cc-api doctor        # 校验兼容性（无凭证可跑）
```

## 运行

```bash
cc-api serve                          # 127.0.0.1:8765
cc-api serve --port 8080
cc-api config --set api_key='"sk-..."'  # 启用鉴权（x-api-key / Bearer）
cc-api config --set mods_dirs='["/path/to/mod"]'
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /v1/messages | Anthropic Messages API（`stream: true` 走 SSE） |
| GET | /v1/models | 模型列表（可配置，默认 opus/sonnet/haiku 别名，透传给 `--model`） |
| GET | /healthz | 存活与 claude 版本 |
| GET | /v1/sessions | 壳内会话一览（扩展接口，非 Anthropic 标准） |
| DELETE | /v1/sessions/{name} | 删壳映射（transcript 保留，可 `claude --resume` 接管） |

```bash
curl -X POST http://127.0.0.1:8765/v1/messages \
  -H 'Content-Type: application/json' \
  -H 'x-cc-session: work' \
  -d '{"model":"sonnet","max_tokens":1024,"stream":true,
       "system":"用中文回答",
       "messages":[{"role":"user","content":"解释下 Raft"}]}'
```

响应是标准 Anthropic SSE（`message_start` / `content_block_start` /
`content_block_delta` / `content_block_stop` / `message_delta` / `message_stop`），
另带 `x-cc-session` 响应头与 body 内 `_ccshell` 扩展字段（session 名、cc_session_id、
turn 数、花费）。

## 语义说明（v1）

- **多轮**：同一 `x-cc-session` 的多次调用自动 `--resume` 同一个 claude 会话，
  首轮 `system` 经 `--append-system-prompt` 注入（保留 cc 自带 system prompt）。
- **工具**：会话内工具（Bash/Read/Edit/Write…及 mods 注册的工具）由 cc 在服务端执行；
  客户端声明 `tools`/`tool_choice` 会返回 400（讲清原因，不静默吞掉）。
- **上游错误直通**：未登录 → 401 `authentication_error`；限流 → 429；过载 → 529。
- 接受但忽略：`max_tokens` 数值、`temperature`、`top_p`、`stop_sequences`
  （turn 预算走配置 `max_budget_usd`）。

## doctor（升级后必跑）

```bash
cc-api doctor
# PASS claude binary on PATH
# PASS claude --version
# PASS required flags advertised      ← flags 有增减会 FAIL
# PASS stream-json envelope probe     ← 无凭证探针，校验 system/assistant/result 信封
# PASS claude auth state              ← 如实报告未登录/已登录
# PASS mods_dirs exist
```

## REA 逆向结论（本壳设计依据）

- `rea doctor`：本环境无反汇编 provider（Hopper/Ghidra/IDA），分析方法为
  REA 6.4.0 + 二进制静态字符串/上下文提取（Bun 单文件 ELF，内嵌 `$bunfs` JS）。
- mods = 插件形态的 UI 交互扩展（`$.ui.notify` / `$.ui.open` / `$.tool.register` /
  `prompt.autocomplete` 等 `$` API，内嵌 `cc-plugin-mods-guide` 为证）；
  公开加载方式只有 `--plugin-dir <dir>` 与 `CLAUDE_CODE_PLUGIN_DIRS`（热重载 dev-mods
  是交互式会话内流程，本壳 v1 不碰）。
- `-p --output-format stream-json` 必须带 `--verbose`（否则直接报错）。
- `--input-format stream-json` 的多轮 stdio 控制协议标注为 SDK-internal
  （`--await-initialize` 帮助原文），本壳刻意不用，改走 `--resume` 公开语义。
- `--session-id` 不可与 `--resume` 同用（除非 `--fork-session`），已在 2.1.296 实测确认。

## 激活

壳本身不碰凭据。真实 turn 需要 claude 先激活（二选一）：

1. `claude auth login`（订阅登录，交互式），或
2. `export ANTHROPIC_API_KEY=...`（API key 直连）

激活后跑一次 `curl POST /v1/messages` 做真 turn 验证即可。
