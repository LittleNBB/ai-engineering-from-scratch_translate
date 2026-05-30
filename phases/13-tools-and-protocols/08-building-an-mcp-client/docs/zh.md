# 构建 MCP 客户端 — 发现、调用、会话管理

> 大多数 MCP 内容发布的是服务器教程，对客户端一笔带过。客户端代码才是艰难编排所在：进程启动、能力协商、跨多服务器的工具列表合并、采样回调、重连和命名空间冲突解决。本课构建一个将三个不同 MCP 服务器提升到一个扁平工具命名空间的多服务器客户端，供模型使用。

**类型：** Build
**语言：** Python（stdlib，多服务器 MCP 客户端）
**前置课程：** Phase 13 · 07（构建 MCP 服务器）
**时间：** ~75 分钟

## 学习目标

- 将 MCP 服务器作为子进程启动，完成 `initialize`，并发送 `notifications/initialized`。
- 维护每个服务器的会话状态（能力、工具列表、最后收到的通知 id）。
- 将多个服务器的工具列表合并到一个命名空间，并处理冲突。
- 将工具调用路由到拥有该工具的服务器，并重组响应。

## 问题

一个真正的 Agent 宿主（Claude Desktop、Cursor、Goose、Gemini CLI）同时加载多个 MCP 服务器。用户可能同时运行一个文件系统服务器、一个 Postgres 服务器和一个 GitHub 服务器。客户端的工作：

1. 启动每个服务器。
2. 独立完成握手。
3. 对每个服务器调用 `tools/list` 并展平结果。
4. 当模型发出 `notes_search` 时，在合并命名空间中查找并路由到正确的服务器。
5. 处理来自任何服务器的通知（`tools/list_changed`）而不阻塞。
6. 在传输层失败时重连。

手动实现所有这些，正是"玩具"和"可用"之间的分界线。官方 SDK 封装了这些，但心智模型必须是你的。

## 核心概念

### 子进程启动

使用 `subprocess.Popen`，参数 `stdin=PIPE, stdout=PIPE, stderr=PIPE`。设 `bufsize=1` 并使用文本模式逐行读取。每个服务器一个进程；客户端为每个服务器持有一个 `Popen` 句柄。

### 每服务器会话状态

每个服务器一个 `Session` 对象，包含：

- `process` — Popen 句柄。
- `capabilities` — 服务器在 `initialize` 时声明的能力。
- `tools` — 最近一次 `tools/list` 的结果。
- `pending` — 请求 id 到等待响应的 promise/future 的映射。

请求本质上是异步的；向服务器 A 发送 `tools/call` 的同时服务器 B 可能正在处理中，不能阻塞。可以使用线程加队列，或 asyncio。

### 合并命名空间

当客户端看到聚合的工具列表时，名称可能冲突。两个服务器可能都暴露了 `search`。客户端有三种选择：

1. **按服务器名加前缀。** `notes/search`、`files/search`。清晰但不美观。
2. **静默先到先得。** 后加载的服务器的 `search` 覆盖先加载的。有风险；隐藏了冲突。
3. **冲突拒绝。** 拒绝加载第二个服务器；通知用户。对安全敏感的宿主最安全。

Claude Desktop 使用按服务器名加前缀。Cursor 使用冲突拒绝并给出清晰错误。VS Code MCP 也采用按服务器名加前缀。

### 路由

合并后，一个分发表将 `tool_name -> session` 映射。模型按名称发出调用；客户端找到会话并向该服务器的 stdin 写入 `tools/call` 消息，然后等待响应。

### Sampling 回调

如果服务器在 `initialize` 时声明了 `sampling` 能力，它可能会发送 `sampling/createMessage` 请求客户端运行其 LLM。客户端必须：

1. 阻塞对该服务器的进一步请求直到采样完成，或者如果其实现支持并发则进行流水线处理。
2. 调用其 LLM 提供商。
3. 将响应回传给服务器。

Lesson 11 深入讲解 sampling。本课为了完整性提供了桩代码。

### 通知处理

`notifications/tools/list_changed` 意味着重新调用 `tools/list`。`notifications/resources/updated` 意味着如果资源正在使用中则重新读取。通知不得产生响应 — 不要尝试确认它们。

一个常见的客户端 bug：在通知到达流中时，`tools/call` 阻塞了读取循环。使用一个后台读取线程将每条消息推送到队列；主线程从队列中取出并分发。

### 重连

传输层可能失败：服务器崩溃、操作系统杀掉了进程、stdio 管道断开。客户端在 stdout 上检测到 EOF 并将会话视为死亡。选项：

- 静默重启服务器并重新握手。适用于纯只读服务器。
- 将失败呈现给用户。适用于有用户可见会话的有状态服务器。

Phase 13 · 09 讲解 Streamable HTTP 的重连语义；stdio 更简单。

### Keepalive 和会话 id

Streamable HTTP 使用 `Mcp-Session-Id` 头。Stdio 没有会话 id — 进程身份本身就是会话。Keepalive ping 是可选的；stdio 管道不会因空闲而断开。

## 使用方法

`code/main.py` 作为子进程启动三个模拟 MCP 服务器，分别握手，合并它们的工具列表，并将工具调用路由到正确的服务器。"服务器"实际上是运行玩具响应器的其他 Python 进程（没有真正的 LLM）。运行它来查看：

- 三次初始化，每次都有自己的能力集。
- 三个 `tools/list` 结果合并为一个 7 工具的命名空间。
- 基于工具名称的路由决策。
- 通过命名空间前缀防止的冲突。

关注要点：

- `Session` dataclass 干净地持有每个服务器的状态。
- 后台读取线程在 stdout 上出队每一行而不阻塞主线程。
- 分发表是一个简单的 `dict[str, Session]`。
- 冲突处理是显式的：当两个服务器声明相同名称时，后者被加上前缀重命名。

## 交付产出

本课产出 `outputs/skill-mcp-client-harness.md`。给定一个声明式的 MCP 服务器列表（name、command、args），该技能生成一个启动它们、合并工具列表、并提供带冲突解析的路由函数的脚手架。

## 练习

1. 运行 `code/main.py`，观察服务器启动日志。用 SIGTERM 杀掉一个模拟服务器进程，观察客户端如何检测 EOF 并将该会话标记为死亡。

2. 实现命名空间前缀。当两个服务器暴露 `search` 时，将第二个重命名为 `<server>/search`。更新分发表并验证工具调用正确路由。

3. 为服务器重启添加连接池风格的退避策略：连续失败时指数退避，上限 30 秒，三次失败后向用户发出通知。

4. 草绘一个支持 100 个并发 MCP 服务器的客户端。什么数据结构替换简单的分发字典？（提示：前缀命名空间用 trie，加上每个服务器工具数量的指标。）

5. 将客户端移植到官方 MCP Python SDK。SDK 封装了 `stdio_client` 和 `ClientSession`。代码应从约 200 行缩减到约 40 行，同时保留多服务器路由。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| MCP Client（MCP 客户端） | "Agent 宿主" | 启动服务器并编排工具调用的进程 |
| Session（会话） | "每服务器状态" | 能力、工具列表和待处理请求的簿记 |
| Merged Namespace（合并命名空间） | "一个工具列表" | 跨所有活跃服务器的扁平工具名称集合 |
| Namespace Collision（命名空间冲突） | "两个服务器同名工具" | 客户端必须加前缀、拒绝或先到先得 |
| Routing（路由） | "谁收到这个调用？" | 从工具名到拥有服务器的分发 |
| Background Reader（后台读取器） | "非阻塞 stdout" | 将服务器 stdout 排空到队列的线程或任务 |
| Sampling Callback（采样回调） | "LLM 即服务" | 客户端对服务器 `sampling/createMessage` 的处理器 |
| `notifications/*_changed` | "原语已变更" | 信号客户端必须重新发现或重新读取 |
| Reconnection Policy（重连策略） | "服务器死了怎么办" | 传输层失败时的重启语义 |
| Stdio Session（Stdio 会话） | "进程 = 会话" | 没有会话 id；子进程生命周期就是会话 |

## 延伸阅读

- [Model Context Protocol — Client spec](https://modelcontextprotocol.io/specification/2025-11-25/client) — 规范性客户端行为
- [MCP — Quickstart client guide](https://modelcontextprotocol.io/quickstart/client) — 使用 Python SDK 的 hello-world 客户端教程
- [MCP Python SDK — client module](https://github.com/modelcontextprotocol/python-sdk) — 参考 `ClientSession` 和 `stdio_client`
- [MCP TypeScript SDK — Client](https://github.com/modelcontextprotocol/typescript-sdk) — TS 并行实现
- [VS Code — MCP in extensions](https://code.visualstudio.com/api/extension-guides/ai/mcp) — VS Code 如何在单个编辑器宿主中多路复用多个 MCP 服务器