# A2A — Agent 间协议

> MCP 是 Agent 到工具。A2A（Agent2Agent）是 Agent 到 Agent — 一个让基于不同框架构建的不透明 Agent 协作的开放协议。由 Google 于 2025 年 4 月发布，2025 年 6 月捐赠给 Linux 基金会，2026 年 4 月达到 v1.0，拥有 150 多个支持者，包括 AWS、Cisco、Microsoft、Salesforce、SAP 和 ServiceNow。它吸收了 IBM 的 ACP 并添加了 AP2 支付扩展。本课讲解 Agent Card、Task 生命周期和两种传输绑定。

**类型：** Build
**语言：** Python（stdlib，Agent Card + Task 脚手架）
**前置课程：** Phase 13 · 06（MCP 基础）、Phase 13 · 08（MCP 客户端）
**时间：** ~75 分钟

## 学习目标

- 区分 Agent 到工具（MCP）与 Agent 到 Agent（A2A）的用例。
- 在 `/.well-known/agent.json` 发布带有技能和端点元数据的 Agent Card。
- 走完 Task 生命周期（submitted → working → input-required → completed / failed / canceled / rejected）。
- 使用带有 Parts（text、file、data）的 Messages 和 Artifacts 作为输出。

## 问题

一个客服 Agent 需要将报告撰写委托给一个专门的写手 Agent。A2A 之前的选项：

- 自定义 REST API。能工作但每对组合都是一次性的。
- 共享代码库。要求两个 Agent 运行相同的框架。
- MCP。不合适：MCP 用于调用工具，而非两个 Agent 在保持各自不透明内部推理的同时协作。

A2A 填补了这个空白。它将交互建模为一个 Agent 向另一个发送 Task，带有生命周期、消息和产出物。被调用 Agent 的内部状态保持不透明 — 调用者只看到任务状态转换和最终输出。

A2A 是"让跨框架的 Agent 互相交谈"的协议。它不替代 MCP；两者是互补的。

## 核心概念

### Agent Card

每个符合 A2A 的 Agent 在 `/.well-known/agent.json` 发布一张卡片：

```json
{
  "schemaVersion": "1.0",
  "name": "research-agent",
  "description": "Summarizes academic papers and drafts citations.",
  "url": "https://research.example.com/a2a",
  "version": "1.2.0",
  "skills": [
    {
      "id": "summarize_paper",
      "name": "Summarize a paper",
      "description": "Read a paper PDF and produce a 3-paragraph summary.",
      "inputModes": ["text", "file"],
      "outputModes": ["text", "artifact"]
    }
  ],
  "capabilities": {"streaming": true, "pushNotifications": true}
}
```

发现基于 URL：获取卡片，了解 A2A 端点的 URL，枚举技能。

### 签名 Agent Card（AP2）

AP2 扩展（2025 年 9 月）为 Agent Card 添加了加密签名。发布者用自己的 JWT 签名卡片；消费者验证。防止冒充。

### Task 生命周期

```
submitted -> working -> completed | failed | canceled | rejected
             -> input_required -> working (通过消息循环)
```

客户端通过 `tasks/send` 发起。被调用 Agent 经历状态转换；客户端通过 SSE 订阅状态更新或轮询。

### Messages 和 Parts

一条消息携带一个或多个 Parts：

- `text` — 纯文本内容。
- `file` — 带 mimeType 的 base64 blob。
- `data` — 类型化 JSON 载荷（给被调用 Agent 的结构化输入）。

示例：

```json
{
  "role": "user",
  "parts": [
    {"type": "text", "text": "Summarize this paper."},
    {"type": "file", "file": {"name": "paper.pdf", "mimeType": "application/pdf", "bytes": "..."}},
    {"type": "data", "data": {"targetLength": "3 paragraphs"}}
  ]
}
```

### Artifacts（产出物）

输出是 Artifacts，而非原始字符串。Artifact 是一个命名的、类型化的输出：

```json
{
  "name": "summary",
  "parts": [{"type": "text", "text": "..."}],
  "mimeType": "text/markdown"
}
```

Artifacts 可以作为块流式传输。调用者累积。

### 两种传输绑定

1. **HTTP 上的 JSON-RPC。** `/a2a` 端点，POST 用于请求，可选 SSE 用于流式传输。默认绑定。
2. **gRPC。** 用于 gRPC 原生的企业环境。

两种绑定承载相同的逻辑消息形式。

### 不透明性保持

一个关键设计原则：被调用 Agent 的内部状态是不透明的。调用者看到任务状态和产出物。被调用 Agent 的思维链、工具调用、子 Agent 委托 — 全部不可见。这与 MCP 不同，MCP 中工具调用是透明的。

原理：A2A 使竞争者可以在不暴露内部的情况下协作。A2A 可以是"调用这个客服 Agent"而调用者不需要了解该 Agent 如何实现服务。

### 时间线

- **2025-04-09。** Google 宣布 A2A。
- **2025-06-23。** 捐赠给 Linux 基金会。
- **2025-08。** 吸收 IBM 的 ACP。
- **2025-09。** AP2 扩展（Agent 支付）发布。
- **2026-04。** v1.0 发布，150 多个支持组织。

### 与 MCP 的关系

| 维度 | MCP | A2A |
|------|-----|-----|
| 用例 | Agent 到工具 | Agent 到 Agent |
| 不透明性 | 透明工具调用 | 不透明内部推理 |
| 典型调用者 | Agent 运行时 | 另一个 Agent |
| 状态 | 工具调用结果 | 带生命周期的 Task |
| 授权 | OAuth 2.1（Phase 13 · 16） | JWT 签名的 Agent Card（AP2） |
| 传输 | Stdio / Streamable HTTP | HTTP 上的 JSON-RPC / gRPC |

当你想调用特定工具时使用 MCP。当你想将整个任务委托给另一个 Agent 时使用 A2A。许多生产系统两者都用：Agent 用 MCP 作为工具层，用 A2A 作为协作层。

## 使用方法

`code/main.py` 实现了一个最简 A2A 脚手架：一个研究 Agent 发布其卡片，一个写手 Agent 接收带有 PDF 和文本指令的 parts 的 `tasks/send`，经历 working → input_required → working → completed 的转换，并返回一个文本 artifact。全部标准库；使用内存传输层以聚焦消息形式。

关注要点：

- Agent Card JSON 形式。
- Task id 分配和状态转换。
- 带混合类型 parts 的 Messages。
- 任务中途的 input-required 分支。
- 完成时的 Artifact 返回。

## 交付产出

本课产出 `outputs/skill-a2a-agent-spec.md`。给定一个应可被其他 Agent 调用的新 Agent，该技能生成 Agent Card JSON、技能 Schema 和端点蓝图。

## 练习

1. 运行 `code/main.py`。追踪完整的 Task 生命周期，包括被调用 Agent 请求澄清的 input-required 暂停。

2. 添加签名 Agent Card。用 HMAC 对卡片的规范 JSON 签名。编写验证器并确认在卡片被篡改时失败。

3. 实现任务流式传输：写手 Agent 通过 SSE 发出三个增量 artifact 块，调用者累积它们。

4. 设计一个封装 MCP 服务器的 A2A Agent。将每个 MCP 工具映射为 A2A 技能。注意权衡 — 失去了什么不透明性？

5. 阅读 A2A v1.0 公告，找出截至 2026 年 4 月没有任何框架实现的那个功能。（提示：它与多跳任务委托有关。）

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| A2A | "Agent 间协议" | 不透明 Agent 协作的开放协议 |
| Agent Card | "`.well-known/agent.json`" | 描述 Agent 技能和端点的发布元数据 |
| Skill（技能） | "一个可调用单元" | Agent 支持的命名操作（类似 MCP 工具） |
| Task（任务） | "委托单元" | 带生命周期和最终产出物的工作项 |
| Message（消息） | "任务输入" | 承载 Parts（text、file、data） |
| Part | "类型化块" | 消息的 `text` / `file` / `data` 元素 |
| Artifact（产出物） | "任务输出" | 完成时返回的命名、类型化输出 |
| AP2 | "Agent 支付协议" | 用于信任和支付的签名 Agent Card 扩展 |
| Opacity（不透明性） | "黑盒协作" | 被调用 Agent 的内部对调用者隐藏 |
| Input-required | "任务暂停" | Agent 需要更多信息时的生命周期状态 |

## 延伸阅读

- [a2a-protocol.org](https://a2a-protocol.org/latest/) — 规范性 A2A 规范
- [a2aproject/A2A — GitHub](https://github.com/a2aproject/A2A) — 参考实现和 SDK
- [Linux Foundation — A2A launch press release](https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents) — 2025 年 6 月治理转移
- [Google Cloud — A2A protocol upgrade](https://cloud.google.com/blog/products/ai-machine-learning/agent2agent-protocol-is-getting-an-upgrade) — 路线图和合作伙伴势头
- [Google Dev — A2A 1.0 milestone](https://discuss.google.dev/t/the-a2a-1-0-milestone-ensuring-and-testing-backward-compatibility/352258) — v1.0 发布说明和向后兼容指导