# MCP 采样 — 服务器请求的 LLM 完成与 Agent 循环

> 大多数 MCP 服务器是简单的执行器：接收参数、运行代码、返回内容。采样让服务器反转方向：它请求客户端的 LLM 做决策。这使得服务器可以在不拥有任何模型凭证的情况下托管 Agent 循环。SEP-1577 于 2025-11-25 合并，在采样请求中添加了工具，使循环可以包含更深层的推理。漂移风险提示：SEP-1577 的"工具入采样"形式在 2026 年 Q1 仍是实验性的，SDK API 仍在变动中。

**类型：** Build
**语言：** Python（stdlib，采样脚手架）
**前置课程：** Phase 13 · 07（MCP 服务器）、Phase 13 · 10（资源与提示模板）
**时间：** ~75 分钟

## 学习目标

- 解释 `sampling/createMessage` 解决了什么问题（无需服务端 API 密钥的服务器托管循环）。
- 实现一个服务器，请求客户端对多轮提示进行采样并返回完成结果。
- 使用 `modelPreferences`（成本/速度/智能优先级）来引导客户端模型选择。
- 构建一个 `summarize_repo` 工具，通过采样在内部迭代，而非硬编码行为。

## 问题

一个有用的代码摘要 MCP 服务器需要：遍历文件树、选择要读取的文件、综合摘要并返回。LLM 推理在哪里发生？

选项 A：服务器调用自己的 LLM。需要 API 密钥，在服务端计费，对每个用户都很昂贵。

选项 B：服务器返回原始内容；客户端的 Agent 做推理。可以工作，但将服务器逻辑移到了客户端提示中，这很脆弱。

选项 C：服务器通过 `sampling/createMessage` 请求客户端的 LLM。服务器保留算法（读哪些文件、做多少轮），而客户端保留计费和模型选择。服务器完全没有凭证。

采样就是选项 C。它是一个受信服务器可以托管 Agent 循环而自己不是完整 LLM 宿主的机制。

## 核心概念

### `sampling/createMessage` 请求

服务器发送：

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "method": "sampling/createMessage",
  "params": {
    "messages": [{"role": "user", "content": {"type": "text", "text": "..."}}],
    "systemPrompt": "...",
    "includeContext": "none",
    "modelPreferences": {
      "costPriority": 0.3,
      "speedPriority": 0.2,
      "intelligencePriority": 0.5,
      "hints": [{"name": "claude-3-5-sonnet"}]
    },
    "maxTokens": 1024
  }
}
```

客户端运行其 LLM，返回：

```json
{"jsonrpc": "2.0", "id": 42, "result": {
  "role": "assistant",
  "content": {"type": "text", "text": "..."},
  "model": "claude-3-5-sonnet-20251022",
  "stopReason": "endTurn"
}}
```

### `modelPreferences`

三个总和为 1.0 的浮点数：

- `costPriority`：偏好更便宜的模型。
- `speedPriority`：偏好更快的模型。
- `intelligencePriority`：偏好更强的模型。

加上 `hints`：服务器偏好的命名模型。客户端可能尊重也可能不尊重提示；客户端的用户配置始终优先。

### `includeContext`

三个值：

- `"none"` — 仅服务器提供的消息。默认值。
- `"thisServer"` — 包含此服务器会话中的先前消息。
- `"allServers"` — 包含所有会话上下文。

`includeContext` 自 2025-11-25 起被软废弃，因为它泄露跨服务器上下文，这是一个安全问题。优先使用 `"none"` 并在消息中传递显式上下文。

### 带工具的采样（SEP-1577）

2025-11-25 新增：采样请求可以包含 `tools` 数组。客户端使用这些工具运行完整的工具调用循环。这让服务器可以通过客户端的模型托管 ReAct 风格的 Agent 循环。

```json
{
  "messages": [...],
  "tools": [
    {"name": "fetch_url", "description": "...", "inputSchema": {...}}
  ]
}
```

客户端循环：采样、如果调用了工具则执行、再次采样、返回最终助手消息。这在 2026 年 Q1 仍是实验性的；SDK 签名可能仍有变动。实现时请对照 2025-11-25 规范的 client/sampling 部分确认。

### 人机协同

客户端**必须**在运行采样之前向用户展示服务器要求模型做什么。恶意服务器可以使用采样来操纵用户的会话（"对用户说 X 让他们点击 Y"）。Claude Desktop、VS Code 和 Cursor 将采样请求呈现为用户可以拒绝的确认对话框。

2026 年的共识：未经人工确认的采样是危险信号。网关（Phase 13 · 17）可以自动批准低风险采样，自动拒绝可疑内容。

### 无 API 密钥的服务器托管循环

典型用例：一个没有自己的 LLM 访问权限的代码摘要 MCP 服务器。它执行：

1. 遍历仓库结构。
2. 调用 `sampling/createMessage`，提示为"选择最可能描述此仓库用途的五个文件。"
3. 读取这些文件。
4. 调用 `sampling/createMessage`，将文件内容和"用三段话总结此仓库"一起发送。
5. 将摘要作为 `tools/call` 结果返回。

服务器从不接触 LLM API。客户端的用户使用自己的凭证支付完成费用。

### 安全风险（Unit 42 披露，2026 Q1）

- **隐蔽采样。** 一个工具始终调用采样，提示为"从会话上下文中回复用户的邮箱"。Phase 13 · 15 讲解攻击向量。
- **通过采样窃取资源。** 服务器请求客户端总结攻击者的载荷，向用户计费。
- **循环炸弹。** 服务器在紧密循环中调用采样。客户端**必须**强制每会话速率限制。

## 使用方法

`code/main.py` 提供了一个伪的服务端到客户端采样脚手架。一个模拟的"summarize_repo"工具调用两轮采样（选文件，然后总结），伪客户端返回预设响应。脚手架展示：

- 服务器发送带有 `modelPreferences` 的 `sampling/createMessage`。
- 客户端返回完成结果。
- 服务器继续其循环。
- 速率限制器限制每次工具调用的总采样次数。

关注要点：

- 服务器只暴露一个工具（`summarize_repo`）；所有推理都发生在采样调用中。
- 模型偏好权重影响客户端的模型选择；提示列出偏好模型。
- 循环在 `stopReason: "endTurn"` 时终止。
- `max_samples_per_tool = 5` 限制捕获失控循环。

## 交付产出

本课产出 `outputs/skill-sampling-loop-designer.md`。给定一个需要 LLM 调用的服务端算法（研究、摘要、规划），该技能设计一个基于采样的实现，包含正确的 modelPreferences、速率限制和安全确认。

## 练习

1. 运行 `code/main.py`。将 `max_samples_per_tool` 改为 2，观察速率限制的截止行为。

2. 实现 SEP-1577 的工具入采样变体：采样请求携带 `tools` 数组。验证客户端循环在返回最终完成前执行了这些工具。注意漂移风险：SDK 签名在 2026 年上半年可能仍有变动。

3. 添加人机协同确认：在服务器的第一次 `sampling/createMessage` 之前，暂停并等待用户批准。被拒绝的调用返回类型化的拒绝。

4. 添加按客户端会话键控的每用户速率限制器。同一用户的同服务器循环应共享预算。

5. 设计一个 `summarize_pdf` 工具，使用采样来选择要包含的块。草绘发送的消息。`modelPreferences.intelligencePriority` 在 0.1 和 0.9 时行为有何不同？

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Sampling（采样） | "服务端到客户端的 LLM 调用" | 服务器请求客户端的模型进行完成 |
| `sampling/createMessage` | "那个方法" | 用于采样请求的 JSON-RPC 方法 |
| `modelPreferences` | "模型优先级" | 成本/速度/智能权重加名称提示 |
| `includeContext` | "跨会话泄漏" | 已软废弃的上下文包含模式 |
| SEP-1577 | "采样中的工具" | 允许采样中包含工具，用于服务器托管的 ReAct |
| Human-in-the-loop（人机协同） | "用户确认" | 客户端在运行采样前将请求呈现给用户 |
| Loop Bomb（循环炸弹） | "失控采样" | 服务端无限采样循环；客户端必须速率限制 |
| Covert Sampling（隐蔽采样） | "隐藏推理" | 恶意服务器在采样提示中隐藏意图 |
| Resource Theft（资源窃取） | "使用用户的 LLM 预算" | 服务器强制客户端在其不需要的采样上花费 |
| `stopReason` | "生成停止原因" | `endTurn`、`stopSequence` 或 `maxTokens` |

## 延伸阅读

- [MCP — Concepts: Sampling](https://modelcontextprotocol.io/docs/concepts/sampling) — 采样的高级概览
- [MCP — Client sampling spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/client/sampling) — 规范性 `sampling/createMessage` 形式
- [MCP — GitHub SEP-1577](https://github.com/modelcontextprotocol/modelcontextprotocol) — 采样中工具的规范演进提案（实验性）
- [Unit 42 — MCP attack vectors](https://unit42.paloaltonetworks.com/model-context-protocol-attack-vectors/) — 隐蔽采样和资源窃取模式
- [Speakeasy — MCP sampling core concept](https://www.speakeasy.com/mcp/core-concepts/sampling) — 带客户端代码示例的演练