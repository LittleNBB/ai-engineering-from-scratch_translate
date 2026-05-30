# MCP 传输层 — stdio vs Streamable HTTP vs SSE 迁移

> stdio 在本地可用，在其他任何地方都不行。Streamable HTTP（2025-03-26）是远程标准。旧的 HTTP+SSE 传输层已被废弃，将在 2026 年中期移除。选错传输层意味着一次迁移；选对则获得一个带会话连续性和 DNS 重绑定防护的可远程托管 MCP 服务器。

**类型：** Learn
**语言：** Python（stdlib，Streamable HTTP 端点骨架）
**前置课程：** Phase 13 · 07、08（MCP 服务器和客户端）
**时间：** ~45 分钟

## 学习目标

- 根据部署形态（本地 vs 远程、单进程 vs 集群）在 stdio 和 Streamable HTTP 之间做出选择。
- 实现 Streamable HTTP 单端点模式：POST 用于请求，GET 用于会话流。
- 强制执行 `Origin` 验证和 session-id 语义以防御 DNS 重绑定。
- 在 2026 年中期移除截止日期之前，将旧版 HTTP+SSE 服务器迁移到 Streamable HTTP。

## 问题

第一个 MCP 远程传输层（2024 年 11 月）是 HTTP+SSE：两个端点，一个用于客户端的 POST，一个 Server-Sent-Events 通道用于服务器到客户端的流。它能工作。但它也很笨重：每个会话两个端点，某些 CDN 前面缓存失效，以及对长连接 SSE 的硬依赖（某些 WAF 会激进地终止它）。

2025-03-26 规范用 Streamable HTTP 替换了它：单个端点，POST 用于客户端请求，GET 用于建立会话流，两者共享 `Mcp-Session-Id` 头。此后构建或迁移的每个服务器都使用 Streamable HTTP。旧的 SSE 模式正在被废弃 — Atlassian Rovo 于 2026 年 6 月 30 日移除；Keboola 于 2026 年 4 月 1 日；大多数剩余的企业服务器在 2026 年底前完成。

stdio 对本地服务器仍然重要。Claude Desktop、VS Code 和每个 IDE 形状的客户端通过 stdio 启动服务器。正确的心智模型：stdio 用于"本机"，Streamable HTTP 用于"跨网络"。没有交叉。

## 核心概念

### stdio

- 子进程传输层。客户端启动服务器，通过 stdin/stdout 通信。
- 一行一个 JSON 对象。换行符分隔。
- 没有会话 id；进程身份就是会话。
- 不需要认证（子进程继承父进程的信任边界）。
- 永远不要用于远程服务器 — 你需要 SSH 或 socat 来隧道传输，到那时不如用 Streamable HTTP。

### Streamable HTTP

单端点 `/mcp`（或任意路径）。支持三种 HTTP 方法：

- **POST /mcp。** 客户端发送 JSON-RPC 消息。服务器回复单个 JSON 响应，或一个 SSE 流包含一个或多个响应（适用于与该请求相关的批处理响应和通知）。
- **GET /mcp。** 客户端打开一个长连接 SSE 通道。服务器用它来发送服务器到客户端的请求（sampling、通知、elicitation）。
- **DELETE /mcp。** 客户端显式终止会话。

会话通过服务器在第一个响应中设置的 `Mcp-Session-Id` 头来标识，客户端在每个后续请求中回显该头。会话 id 必须是加密随机的（128+ 位）；客户端选择的 id 会被拒绝以确保安全。

### 单端点 vs 双端点

旧规范中的双端点模式在 2026 年仍可调用 — 规范将其声明为"遗留兼容"。但所有新服务器应使用单端点。官方 SDK 生成单端点；仅在与未迁移的远程服务器通信时才使用遗留模式。

### `Origin` 验证和 DNS 重绑定

浏览器目前不是 MCP 客户端，但攻击者可以构造一个网页，说服浏览器向 `localhost:1234/mcp` 发送 POST — 而用户的本地 MCP 服务器正在监听。如果服务器不检查 `Origin`，浏览器的同源策略无法保护它，因为 `Origin: http://evil.com` 是合法的跨域来源。

2025-11-25 规范要求服务器拒绝 `Origin` 不在允许列表中的请求。允许列表通常包含 MCP 客户端宿主（`https://claude.ai`、`vscode-webview://*`）和本地 UI 的 localhost 变体。

### 会话 id 生命周期

1. 客户端发送第一个请求时不带 `Mcp-Session-Id`。
2. 服务器分配一个随机 id，在响应头中设置 `Mcp-Session-Id`。
3. 客户端在所有后续请求和 `GET /mcp` 流中回显该头。
4. 服务器可以撤销会话；客户端在后续请求中看到 404，必须重新初始化。
5. 客户端可以显式 DELETE 会话以干净关闭。

### Keepalive 和重连

SSE 连接会断开。客户端通过使用相同的 `Mcp-Session-Id` 重新 GET 来重建连接。服务器必须排队在断线期间错过的事件（在合理的窗口内），并通过客户端回显的 `last-event-id` 头进行重放。

Phase 13 · 13 讲解 Tasks，它可以让长时间运行的工作在全会话重连时也能存活。

### 向后兼容探测

一个想要同时支持新旧服务器的客户端：

1. POST 到 `/mcp`。
2. 如果响应是 `200 OK` 加 JSON 或 SSE，这是 Streamable HTTP。
3. 如果响应是 `200 OK` 加 `Content-Type: text/event-stream` 并且有一个指向次级端点的 `Location` 头，这是旧版 HTTP+SSE；跟随 `Location`。

### Cloudflare、ngrok 和托管

2026 年的生产远程 MCP 服务器运行在 Cloudflare Workers（配合其 MCP Agents SDK）、Vercel Functions 或容器化的 Node/Python 上。关键点：你的托管必须支持 SSE GET 的长连接。Vercel 的免费层限制 10 秒，不适合。Cloudflare Workers 支持无限期流。

### 网关组合

当你用网关（Phase 13 · 17）前置多个 MCP 服务器时，网关是一个单 Streamable HTTP 端点，它重写会话 id 并多路复用上游。工具在网关层合并；客户端看到的是一个单一的逻辑服务器。

### 传输层失败模式

- **stdio SIGPIPE。** 写入过程中子进程死亡会触发 SIGPIPE；服务器应干净退出。客户端应检测 EOF 并标记会话为死亡。
- **HTTP 502 / 504。** Cloudflare、nginx 和其他代理在上游失败时发出这些。Streamable HTTP 客户端应在短退避后重试一次。
- **SSE 连接断开。** TCP RST、代理超时或客户端网络变化关闭了流。客户端用 `Mcp-Session-Id` 和可选的 `last-event-id` 重连以恢复。
- **会话撤销。** 服务器使会话 id 失效；客户端在下次请求时看到 404。客户端必须重新握手。
- **时钟偏差。** 客户端的资源 TTL 计算与服务器不一致。客户端应将服务器时间戳视为权威。

### 何时绕过 Streamable HTTP

某些企业在自己的网络内将 MCP 服务器部署在 gRPC 或消息队列传输层后面。这是非标准的 — MCP 规范没有正式定义这些。网关可以对 MCP 客户端暴露 Streamable HTTP 表面，同时内部使用 gRPC。保持外部表面符合规范；网关负责翻译。

## 使用方法

`code/main.py` 使用 `http.server`（标准库）实现了一个最简的 Streamable HTTP 端点。它在 `/mcp` 上处理 POST、GET 和 DELETE，在第一个响应时设置 `Mcp-Session-Id`，验证 `Origin`，并拒绝来自非允许列表来源的请求。处理器复用了 Lesson 07 笔记服务器的分发逻辑。

关注要点：

- POST 处理器读取 JSON-RPC 体，分发，并写入 JSON 响应（单响应变体；SSE 变体结构类似）。
- `Origin` 检查拒绝默认的 `http://evil.example` 探测但接受 `http://localhost`。
- 会话 id 是随机的 128 位十六进制字符串；服务器在内存中保持每会话状态。

## 交付产出

本课产出 `outputs/skill-mcp-transport-migrator.md`。给定一个 HTTP+SSE（遗留）MCP 服务器，该技能生成一个迁移到 Streamable HTTP 的计划，包含会话 id 连续性、Origin 检查和向后兼容探测支持。

## 练习

1. 运行 `code/main.py`。用 `curl` 发送一个 `initialize` 的 POST 并观察 `Mcp-Session-Id` 响应头。发送第二个请求回显该头，验证会话连续性。

2. 添加一个 GET 处理器来打开 SSE 流。每五秒发送一个 `notifications/progress` 事件。通过用相同的 session id 重新 GET 来重连，确认服务器接受它。

3. 实现 `last-event-id` 重放逻辑。在重连时，重放自该 id 以来生成的所有事件。

4. 扩展 `Origin` 验证以支持通配符模式（`https://*.example.com`），确认它接受 `https://app.example.com` 但拒绝 `https://evil.example.com.attacker.net`。

5. 从官方注册表中取一个旧版 HTTP+SSE 服务器（有好几个），草绘迁移方案：端点处理、会话 id 生成和头语义需要哪些变更。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Stdio Transport（Stdio 传输层） | "本地子进程" | stdin/stdout 上的 JSON-RPC，换行符分隔 |
| Streamable HTTP | "远程传输层" | 单端点 POST + GET + 可选 SSE，2025-03-26 规范 |
| HTTP+SSE | "旧版" | 将在 2026 年中期移除的双端点模型 |
| `Mcp-Session-Id` | "会话头" | 服务器分配的随机 id，在每个后续请求中回显 |
| `Origin` 允许列表 | "DNS 重绑定防护" | 拒绝 Origin 未被批准的请求 |
| Single Endpoint（单端点） | "一个 URL" | `/mcp` 处理所有会话操作的 POST / GET / DELETE |
| `last-event-id` | "SSE 重放" | 用于在不丢失事件的情况下恢复断开流的头 |
| Backwards-compat Probe（向后兼容探测） | "新旧检测" | 客户端响应形式检查，自动选择传输层 |
| Long-lived HTTP（长连接 HTTP） | "SSE 流式传输" | 服务器在一条 TCP 连接上推送几分钟或几小时的事件 |
| Session Revocation（会话撤销） | "强制重新初始化" | 服务器使会话 id 失效；客户端必须重新握手 |

## 延伸阅读

- [MCP — Basic transports spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) — stdio 和 Streamable HTTP 的规范性参考
- [MCP — Basic transports spec 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — 引入 Streamable HTTP 的修订版
- [Cloudflare — MCP transport](https://developers.cloudflare.com/agents/model-context-protocol/transport/) — Workers 托管的 Streamable HTTP 模式
- [AWS — MCP transport mechanisms](https://builder.aws.com/content/35A0IphCeLvYzly9Sw40G1dVNzc/mcp-transport-mechanisms-stdio-vs-streamable-http) — 跨部署形态的比较
- [Atlassian — HTTP+SSE deprecation notice](https://community.atlassian.com/forums/Atlassian-Remote-MCP-Server/HTTP-SSE-Deprecation-Notice/ba-p/3205484) — 具体的迁移截止日期示例