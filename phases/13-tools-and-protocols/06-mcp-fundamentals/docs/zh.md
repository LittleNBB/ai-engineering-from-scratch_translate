# MCP 基础 — 原语、生命周期、JSON-RPC 基底

> MCP 之前的每个集成都是一次性的。Model Context Protocol（模型上下文协议）由 Anthropic 于 2024 年 11 月首次发布，现由 Linux 基金会的 Agentic AI Foundation 管理，它标准化了发现和调用流程，使任何客户端都能与任何服务器对话。2025-11-25 规范定义了六个原语（三个服务端、三个客户端）、三阶段生命周期和 JSON-RPC 2.0 线路格式。掌握这些内容后，本阶段 MCP 章节的其余部分就只是阅读了。

**类型：** Learn
**语言：** Python（stdlib，JSON-RPC 解析器）
**前置课程：** Phase 13 · 01 到 05（工具接口与 Function Calling）
**时间：** ~45 分钟

## 学习目标

- 列出所有六个 MCP 原语（服务端：tools、resources、prompts；客户端：roots、sampling、elicitation），并各举一个用例。
- 走完三阶段生命周期（initialize、operation、shutdown），说明每阶段由谁发送什么消息。
- 解析和生成 JSON-RPC 2.0 的请求、响应和通知信封。
- 解释 `initialize` 时的能力协商是什么，以及没有它会怎样。

## 问题

在 MCP 之前，每个使用工具的 Agent 都有自己的协议。Cursor 有一个形似 MCP 但不兼容的工具系统。Claude Desktop 带着另一个。VS Code 的 Copilot 扩展是第三种。一个构建"Postgres 查询"工具的团队要写三遍，分别适配三个不同的宿主 API。要复用它就得复制代码。

结果就是一次性集成的寒武纪大爆发，以及生态发展速度的天花板。

MCP 通过标准化线路格式来修复这个问题。一个 MCP Server 可以在每个 MCP Client 中工作：Claude Desktop、ChatGPT、Cursor、VS Code、Gemini、Goose、Zed、Windsurf — 截至 2026 年 4 月已有 300 多个客户端。每月 1.1 亿次 SDK 下载。10,000 多个公开服务器。Linux 基金会于 2025 年 12 月在新成立的 Agentic AI Foundation 下接管了管理权。

本阶段使用的规范版本是 **2025-11-25**。它增加了异步 Tasks（SEP-1686）、URL 模式的 elicitation（SEP-1036）、带工具的 sampling（SEP-1577）、增量范围同意（SEP-835）以及 OAuth 2.1 资源指示器语义。Phase 13 · 09 到 16 涵盖这些扩展。本课只讲基础部分。

## 核心概念

### 三个服务端原语

1. **Tools（工具）。** 可调用的动作。和 Phase 13 · 01 的四步循环一样。
2. **Resources（资源）。** 暴露的数据。按 URI 寻址的只读内容：`file:///path`、`db://query/...`、自定义 scheme。
3. **Prompts（提示模板）。** 可复用的模板。宿主 UI 中的斜杠命令（slash commands）；服务器提供模板，客户端填充参数。

### 三个客户端原语

4. **Roots（根目录）。** 服务器被允许访问的 URI 集合。客户端声明它们；服务器遵守它们。
5. **Sampling（采样）。** 服务器请求客户端的模型执行一次完成。使服务器可以在没有服务端 API 密钥的情况下运行 Agent 循环。
6. **Elicitation（引出）。** 服务器在执行过程中向客户端的用户请求结构化输入。表单或 URL（SEP-1036）。

MCP 中的每个能力都精确属于这六个之一。Phase 13 · 10 到 14 会逐一深入讲解。

### 线路格式：JSON-RPC 2.0

每条消息都是一个包含以下字段的 JSON 对象：

- 请求（Requests）：`{jsonrpc: "2.0", id, method, params}`。
- 响应（Responses）：`{jsonrpc: "2.0", id, result | error}`。
- 通知（Notifications）：`{jsonrpc: "2.0", method, params}` — 没有 `id`，不需要响应。

基础规范约有 15 个方法，按原语分组。重要的有：

- `initialize` / `initialized`（握手）
- `tools/list`、`tools/call`
- `resources/list`、`resources/read`、`resources/subscribe`
- `prompts/list`、`prompts/get`
- `sampling/createMessage`（服务器到客户端）
- `notifications/tools/list_changed`、`notifications/resources/updated`、`notifications/progress`

### 三阶段生命周期

**阶段 1：initialize（初始化）。**

客户端发送 `initialize`，附带自己的 `capabilities` 和 `clientInfo`。服务器回复自己的 `capabilities`、`serverInfo` 和它所支持的规范版本。客户端消化完响应后发送 `notifications/initialized`。此后，双方可以根据协商的能力互相发送请求。

**阶段 2：operation（运行）。**

双向通信。客户端调用 `tools/list` 来发现工具，然后调用 `tools/call` 来执行。如果服务器声明了该能力，可以发送 `sampling/createMessage`。当服务器的工具集发生变化时，可以发送 `notifications/tools/list_changed`。当用户更改根目录范围时，客户端可以发送 `notifications/roots/list_changed`。

**阶段 3：shutdown（关闭）。**

任一方关闭传输层。MCP 中没有结构化的关闭方法；传输层（stdio 或 Streamable HTTP，Phase 13 · 09）承载连接结束信号。

### 能力协商

`initialize` 握手中的 `capabilities` 就是契约。服务器示例：

```json
{
  "tools": {"listChanged": true},
  "resources": {"subscribe": true, "listChanged": true},
  "prompts": {"listChanged": true}
}
```

服务器声明它可以发出 `tools/list_changed` 通知并支持 `resources/subscribe`。客户端通过声明自己的能力来同意：

```json
{
  "roots": {"listChanged": true},
  "sampling": {},
  "elicitation": {}
}
```

如果客户端没有声明 `sampling`，服务器不得调用 `sampling/createMessage`。对称地：如果服务器没有声明 `resources.subscribe`，客户端不得尝试订阅。

这正是防止生态漂移的机制。不支持 sampling 的客户端仍然是有效的 MCP Client；不调用 `sampling` 的服务器仍然是有效的 MCP Server。它们只是不一起使用那个功能。

### 结构化内容和错误形式

`tools/call` 返回一个类型化 block 的 `content` 数组：`text`、`image`、`resource`。Phase 13 · 14 会添加 MCP Apps（`ui://` 交互式 UI）。

错误使用 JSON-RPC 错误码。规范定义的新增项：`-32002` "Resource not found"、`-32603` "Internal error"，加上 MCP 特有的错误数据 `error.data`。

### 客户端能力 vs 工具调用细节

一个常见的混淆点：`capabilities.tools` 是关于客户端是否支持工具列表变更通知的。客户端**是否**调用特定工具是运行时由模型驱动的选择，不是能力标志。能力标志是规范级的契约。模型的选择是正交的。

### 为什么用 JSON-RPC 而不是 REST？

JSON-RPC 2.0（2010 年）是一个轻量级双向协议。REST 是客户端发起的。MCP 需要服务器发起的消息（sampling、通知），因此具有对称请求/响应形式的 JSON-RPC 是自然之选。JSON-RPC 还能干净地组合在 stdio 和 WebSocket/Streamable HTTP 之上，无需重新发明 HTTP 的请求形式。

## 使用方法

`code/main.py` 提供了一个最简的 JSON-RPC 2.0 解析器和生成器，然后手动走一遍 `initialize` → `tools/list` → `tools/call` → `shutdown` 序列，打印每条消息。不使用真实传输层；只关注消息形式。对照延伸阅读中链接的规范来验证每个信封。

关注要点：

- `initialize` 双向声明能力；响应包含 `serverInfo` 和 `protocolVersion: "2025-11-25"`。
- `tools/list` 返回一个 `tools` 数组；每个条目包含 `name`、`description`、`inputSchema`。
- `tools/call` 使用 `params.name` 和 `params.arguments`。
- 响应的 `content` 是一个 `{type, text}` block 数组。

## 交付产出

本课产出 `outputs/skill-mcp-handshake-tracer.md`。给定一个 pcap 风格的 MCP 客户端-服务器交互记录，该技能会为每条消息标注它属于哪个原语、哪个生命周期阶段、以及依赖哪个能力。

## 练习

1. 运行 `code/main.py`。找出能力协商发生的那一行，并描述如果服务器没有声明 `tools.listChanged` 会有什么变化。

2. 扩展解析器以处理 `notifications/progress`。消息形式：`{method: "notifications/progress", params: {progressToken, progress, total}}`。在一个长时间运行的 `tools/call` 进行中发出它，确认客户端处理器会显示进度条。

3. 从头到尾阅读 MCP 2025-11-25 规范 — 整个文档约 80 页。找出大多数服务器不需要的那个能力标志。提示：它与资源订阅相关。

4. 在纸上草绘一个假设的"定时任务"（cron job）功能应归属哪个原语。（提示：服务器希望客户端在计划时间调用它。目前六个原语都不适用。）MCP 的 2026 路线图有一个相关的 SEP 草案。

5. 从 GitHub 上的一个开源 MCP 服务器解析一个会话日志。统计请求、响应和通知消息的数量。计算生命周期流量与运行流量的占比。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| MCP | "Model Context Protocol" | 模型到工具的发现和调用的开放协议 |
| Server Primitive（服务端原语） | "服务器暴露的内容" | tools（动作）、resources（数据）、prompts（模板） |
| Client Primitive（客户端原语） | "客户端允许服务器使用的" | roots（范围）、sampling（LLM 回调）、elicitation（用户输入） |
| JSON-RPC 2.0 | "线路格式" | 对称的请求/响应/通知信封 |
| `initialize` 握手 | "能力协商" | 第一对消息；服务器和客户端声明支持的功能 |
| `tools/list` | "发现" | 客户端向服务器请求当前工具集 |
| `tools/call` | "调用" | 客户端请求服务器用参数执行工具 |
| `notifications/*_changed` | "变更事件" | 服务器告诉客户端其原语列表已改变 |
| Content Block（内容块） | "类型化结果" | 工具结果中的 `{type: "text" | "image" | "resource" | "ui_resource"}` |
| SEP | "Spec Evolution Proposal（规范演进提案）" | 命名的草案提案（如 SEP-1686 异步 Tasks） |

## 延伸阅读

- [Model Context Protocol — Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) — 规范性文档
- [Model Context Protocol — Architecture concepts](https://modelcontextprotocol.io/docs/concepts/architecture) — 六原语心智模型
- [Anthropic — Introducing the Model Context Protocol](https://www.anthropic.com/news/model-context-protocol) — 2024 年 11 月发布文章
- [MCP blog — First MCP anniversary](https://blog.modelcontextprotocol.io/posts/2025-11-25-first-mcp-anniversary/) — 一周年回顾和 2025-11-25 规范变更
- [WorkOS — MCP 2025-11-25 spec update](https://workos.com/blog/mcp-2025-11-25-spec-update) — SEP-1686、1036、1577、835 和 1724 的摘要