# MCP 资源与提示模板 — 工具之外的上下文暴露

> 工具占了 MCP 90% 的关注度。另外两个服务端原语解决的是不同的问题。资源暴露数据供读取；提示模板将可复用模板作为斜杠命令暴露。很多服务器应该用资源而不是把读取包装成工具，用提示模板而不是在客户端提示中硬编码工作流。本课说明决策规则，并走一遍 `resources/*` 和 `prompts/*` 消息。

**类型：** Build
**语言：** Python（stdlib，resource + prompt 处理器）
**前置课程：** Phase 13 · 07（MCP 服务器）
**时间：** ~45 分钟

## 学习目标

- 对给定域中的能力，决定应暴露为工具、资源还是提示模板。
- 实现 `resources/list`、`resources/read`、`resources/subscribe` 并处理 `notifications/resources/updated`。
- 实现带参数模板的 `prompts/list` 和 `prompts/get`。
- 识别宿主何时将提示模板呈现为斜杠命令 vs 自动注入上下文。

## 问题

一个朴素的笔记应用 MCP 服务器将所有东西都暴露为工具：`notes_read`、`notes_list`、`notes_search`。这将每次数据访问都包装成了模型驱动的工具调用。后果：

- 模型必须决定是否对每个可能需要上下文的查询都调用 `notes_read`。
- 只读内容无法被订阅或流式传输到宿主的侧边面板。
- 客户端 UI（Claude Desktop 的资源附加面板、Cursor 的"Include file"选择器）无法呈现数据。

正确的分离方式：将数据暴露为资源，将变更或计算动作暴露为工具，将可复用的多步骤工作流暴露为提示模板。每个原语都有其 UX 交互方式和访问模式。

## 核心概念

### 工具 vs 资源 vs 提示模板 — 决策规则

| 能力 | 原语 |
|------|------|
| 用户想搜索、过滤或转换数据 | 工具（tool） |
| 用户希望宿主将此数据作为上下文包含 | 资源（resource） |
| 用户想要一个可重复运行的模板化工作流 | 提示模板（prompt） |

准则：如果模型在每次相关查询中都受益于调用它，它是工具。如果用户受益于将它附加到对话中，它是资源。如果整个多步骤工作流是用户想复用的单元，它是提示模板。

### 资源

`resources/list` 返回 `{resources: [{uri, name, mimeType, description?}]}`。`resources/read` 接收 `{uri}` 并返回 `{contents: [{uri, mimeType, text | blob}]}`。

URI 可以是任何可寻址的：

- `file:///Users/alice/notes/mcp.md`
- `postgres://my-db/query/SELECT ...`
- `notes://note-14`（自定义 scheme）
- `memory://session-2026-04-22/recent`（服务器特定）

`contents[]` 同时支持文本和二进制。二进制使用 `blob` 作为 base64 编码字符串加上 `mimeType`。

### 资源订阅

在能力中声明 `{resources: {subscribe: true}}`。客户端调用 `resources/subscribe {uri}`。当资源变更时，服务器发送 `notifications/resources/updated {uri}`。客户端重新读取。

用例：一个笔记服务器，其资源是磁盘上的文件；文件监视器触发更新通知；Claude Desktop 在文件于宿主外被编辑时重新拉取文件到上下文中。

### 资源模板（2025-11-25 新增）

`resourceTemplates` 让你暴露参数化的 URI 模式：`notes://{id}`，`id` 作为补全目标。客户端可以在资源选择器中自动补全 id。

### 提示模板

`prompts/list` 返回 `{prompts: [{name, description, arguments?}]}`。`prompts/get` 接收 `{name, arguments}` 并返回 `{description, messages: [{role, content}]}`。

提示模板是一个填充为消息列表的模板，宿主将其喂给模型。例如，一个 `code_review` 提示模板接收一个 `file_path` 参数，返回一个三消息序列：一个系统消息、一个包含文件内容的用户消息和一个带推理模板的助手开场。

### 宿主与提示模板

Claude Desktop、VS Code 和 Cursor 将提示模板作为聊天 UI 中的斜杠命令呈现。用户输入 `/code_review` 并从表单中选择参数。服务器的提示模板是"用户快捷方式"和"发送给模型的完整提示"之间的契约。

并非每个客户端都支持提示模板 — 查看能力协商。一个声明了提示能力但客户端不支持提示的服务器根本看不到斜杠命令。

### "列表变更"通知

资源和提示模板在集合变更时都会发出 `notifications/list_changed`。一个刚导入 20 条新笔记的笔记服务器发出 `notifications/resources/list_changed`；客户端重新调用 `resources/list` 来获取新增内容。

### 内容类型约定

文本：`mimeType: "text/plain"`、`text/markdown`、`application/json`。
二进制：`image/png`、`application/pdf`，加上 `blob` 字段。
MCP Apps（Lesson 14）：`ui://` URI 中的 `text/html;profile=mcp-app`。

### 动态资源

资源 URI 不必对应静态文件。`notes://recent` 每次读取都可以返回最新的五条笔记。`db://query/users/active` 可以执行参数化查询。服务器可以自由地动态计算内容。

规则：如果客户端可以按 URI 缓存，URI 必须稳定。如果计算是一次性的，URI 应包含时间戳或随机数，以免客户端缓存过期。

### 订阅 vs 轮询

支持订阅的客户端通过 `notifications/resources/updated` 获取服务器推送。预订阅客户端或不支持它的宿主通过重新读取来轮询。两者都符合规范。服务器的能力声明告诉客户端它支持哪种。

订阅的成本：服务器上的每会话状态（谁订阅了什么）。保持订阅集有界；断开的客户端应超时。

### 提示模板 vs 系统提示

MCP 中的提示模板不是系统提示。宿主的系统提示（它自己的操作指令）和 MCP 提示模板（服务器提供的、由用户调用的模板）并存。行为良好的客户端永远不会让服务器提示覆盖自己的系统提示；它是分层的。

## 使用方法

`code/main.py` 在 Lesson 07 的笔记服务器基础上扩展了：

- 每条笔记的资源（`notes://note-1` 等），支持 `resources/subscribe`。
- 一个 `review_note` 提示模板，渲染为三消息模板。
- 一个文件监视器模拟，在笔记修改时发出 `notifications/resources/updated`。
- 一个 `notes://recent` 动态资源，始终返回最新的五条笔记。

运行演示来查看完整流程。

## 交付产出

本课产出 `outputs/skill-primitive-splitter.md`。给定一个拟建的 MCP 服务器，该技能将每个能力分类为工具 / 资源 / 提示模板，并给出理由。

## 练习

1. 运行 `code/main.py`。观察初始资源列表，然后触发一次笔记编辑，验证 `notifications/resources/updated` 事件触发。

2. 添加一个 `notifications/resources/list_changed` 发出器：当创建新笔记时，发送通知以便客户端重新发现。

3. 为一个 GitHub MCP 服务器设计三个提示模板：`summarize_pr`、`triage_issue`、`release_notes`。每个都带参数 Schema。提示模板体应无需进一步编辑即可运行。

4. 取 Lesson 07 服务器中的一个现有工具，判断它应继续作为工具还是应拆分为资源加工具对。用一句话论证。

5. 阅读规范的 `server/resources` 和 `server/prompts` 部分。找出 `resources/read` 中那个很少被填充但规范支持的字段。提示：看资源内容上的 `_meta`。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Resource（资源） | "暴露的数据" | 宿主可读的 URI 可寻址内容 |
| Resource URI（资源 URI） | "数据指针" | 带 scheme 前缀的标识符（`file://`、`notes://` 等） |
| `resources/subscribe` | "监视变更" | 客户端选择加入的特定 URI 服务器推送更新 |
| `notifications/resources/updated` | "资源已变更" | 通知客户端订阅的资源有新内容 |
| Resource Template（资源模板） | "参数化 URI" | 带宿主选择器补全提示的 URI 模式 |
| Prompt（提示模板） | "斜杠命令模板" | 带参数槽的命名多消息模板 |
| Prompt Arguments（提示参数） | "模板输入" | 宿主在渲染前收集的类型化参数 |
| `prompts/get` | "渲染模板" | 服务器返回填充后的消息列表 |
| Content Block（内容块） | "类型化块" | `{type: text | image | resource | ui_resource}` |
| Slash-command UX（斜杠命令 UX） | "用户快捷方式" | 宿主将提示模板呈现为以 `/` 开头的命令 |

## 延伸阅读

- [MCP — Concepts: Resources](https://modelcontextprotocol.io/docs/concepts/resources) — 资源 URI、订阅和模板
- [MCP — Concepts: Prompts](https://modelcontextprotocol.io/docs/concepts/prompts) — 提示模板和斜杠命令集成
- [MCP — Server resources spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/resources) — 完整的 `resources/*` 消息参考
- [MCP — Server prompts spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts) — 完整的 `prompts/*` 消息参考
- [MCP — Protocol info site: resources](https://modelcontextprotocol.info/docs/concepts/resources/) — 对官方文档的社区扩展指南