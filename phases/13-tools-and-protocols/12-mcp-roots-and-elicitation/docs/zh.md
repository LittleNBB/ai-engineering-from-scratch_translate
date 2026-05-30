# 根目录与引出 — 范围限定与中途用户输入

> 硬编码路径在用户打开不同项目时就会失效。预填充的工具参数在用户指定不足时会出错。根目录将服务器限定在用户控制的 URI 集合内；引出在工具调用中途暂停，通过表单或 URL 向用户请求结构化输入。两个客户端原语，修复两种常见的 MCP 失败模式。SEP-1036（URL 模式引出，2025-11-25）在 2026 年上半年仍是实验性的 — 使用前请检查 SDK 版本。

**类型：** Build
**语言：** Python（stdlib，roots + elicitation 演示）
**前置课程：** Phase 13 · 07（MCP 服务器）
**时间：** ~45 分钟

## 学习目标

- 声明 `roots` 并响应 `notifications/roots/list_changed`。
- 将服务器的文件操作限制在声明的根目录集合内的 URI 中。
- 使用 `elicitation/create` 在工具调用中途向用户请求确认或结构化输入。
- 在表单模式和 URL 模式引出之间选择（后者是实验性的；有漂移风险）。

## 问题

笔记 MCP 服务器在生产中遇到的两个具体失败。

**路径假设失效。** 服务器是针对 `~/notes` 编写的。一个在不同机器上、笔记在 `~/Documents/Notes` 中的用户，工具调用会静默失败（找不到文件）或更糟，写到了错误的地方。

**用户知道但缺少的参数。** 用户说"删除旧的 TPS 报告笔记"。模型调用 `notes_delete(title: "TPS report")`，但有三条分别来自 2023、2024 和 2025 年的匹配笔记。工具无法猜测。以"有歧义"失败很烦人；对三条都执行则是灾难性的。

根目录修复第一个问题：客户端在 `initialize` 时声明服务器可以访问的 URI 集合。引出修复第二个问题：服务器暂停工具调用并发送 `elicitation/create` 让用户选择是哪一条。

## 核心概念

### 根目录（Roots）

客户端在 `initialize` 时声明根目录列表：

```json
{
  "capabilities": {"roots": {"listChanged": true}}
}
```

服务器随后可以调用 `roots/list`：

```json
{"roots": [{"uri": "file:///Users/alice/Documents/Notes", "name": "Notes"}]}
```

服务器**必须**将根目录视为边界：根目录集合之外的任何文件读写都应被拒绝。这不是由客户端强制执行的（服务器仍然是用户信任的代码），但符合规范的服务器会遵守它。

当用户添加或删除根目录时，客户端发送 `notifications/roots/list_changed`。服务器重新调用 `roots/list` 并更新其边界。

### 为什么根目录是客户端原语

根目录由客户端声明，因为它们代表用户的同意模型。用户告诉 Claude Desktop "让这个笔记服务器访问这两个目录"。服务器不能扩大这个范围。

### 引出（Elicitation）：表单模式默认

`elicitation/create` 接收一个表单 Schema 加一条自然语言提示：

```json
{
  "method": "elicitation/create",
  "params": {
    "message": "Delete 'TPS report'? Multiple notes match; pick one.",
    "requestedSchema": {
      "type": "object",
      "properties": {
        "note_id": {
          "type": "string",
          "enum": ["note-3", "note-7", "note-14"]
        },
        "confirm": {"type": "boolean"}
      },
      "required": ["note_id", "confirm"]
    }
  }
}
```

客户端渲染表单，收集用户的回答，返回：

```json
{
  "action": "accept",
  "content": {"note_id": "note-14", "confirm": true}
}
```

三种可能的 action：`accept`（用户填写了）、`decline`（用户关闭了）、`cancel`（用户中止了整个工具调用）。

表单 Schema 是扁平的 — v1 不支持嵌套对象。SDK 通常拒绝超过单层的复杂结构。

### 引出：URL 模式（SEP-1036，实验性）

2025-11-25 新增。服务器发送一个 URL 而非 Schema：

```json
{
  "method": "elicitation/create",
  "params": {
    "message": "Sign in to GitHub",
    "url": "https://github.com/login/oauth/authorize?client_id=..."
  }
}
```

客户端在浏览器中打开 URL，等待完成，用户返回后返回结果。适用于 OAuth 流程、支付授权和文档签署等表单不够用的场景。

漂移风险提示：SEP-1036 的响应形式仍在变动中；某些 SDK 返回回调 URL，另一些返回完成 token。在生产中使用 URL 模式前请阅读 SDK 的发布说明。

### 何时引出是正确的工具

- 有副作用动作前的用户确认（destructive hint + elicitation）。
- 消歧（从 N 个匹配中选一个）。
- 首次运行设置（API 密钥、目录、偏好）。
- OAuth 风格流程（URL 模式）。

### 何时引出是错误的

- 填充工具的必需参数，而模型本来可以用文字询问。使用普通的重新提示，而不是引出对话框。
- 高频调用。引出会中断对话；不要在循环中触发它。
- 服务器可以在事后验证的内容。验证，返回错误，让模型用文本询问用户。

### 人机协同桥梁

引出与采样一起实现了 MCP 的"人机协同"模型。服务器的 Agent 循环可以为用户输入（引出）或模型推理（采样）而暂停。Phase 13 · 11 讲了采样；本课讲引出。将它们组合在一起，实现完整的循环中途控制。

## 使用方法

`code/main.py` 在笔记服务器基础上扩展了：

- `roots/list` 响应，服务器在根目录列表变更通知后重新查询。
- 一个 `notes_delete` 工具，当多条笔记匹配时使用 `elicitation/create` 来消歧。
- 一个 `notes_setup` 工具，使用 URL 模式引出打开首次运行配置页面（模拟）。
- 一个边界检查，拒绝声明的根目录之外 URI 上的操作。

演示运行三个场景：正常路径（一个匹配）、消歧（三个匹配，引出触发）、根目录外写入（被拒绝）。

## 交付产出

本课产出 `outputs/skill-elicitation-form-designer.md`。给定一个可能需要用户确认或消歧的工具，该技能设计引出表单 Schema 和消息模板。

## 练习

1. 运行 `code/main.py`。触发消歧路径；确认模拟用户的回答被路由回工具。

2. 添加一个新工具 `notes_archive`，每次都需要引出确认（destructive hint）。检查 UX：与模型用文字重新询问相比如何？

3. 为首次运行 OAuth 流程实现 URL 模式引出。注意漂移风险并添加 SDK 版本防护。

4. 扩展 `roots/list` 处理：当通知到达时，服务器应原子性地重新读取并重新扫描可能现在超出范围的已打开文件句柄。

5. 阅读 GitHub 上 SEP-1036 issue 的讨论线程。找出一个影响服务器如何处理 URL 模式回调的未解决问题。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Root（根目录） | "同意边界" | 客户端允许服务器访问的 URI |
| `roots/list` | "服务器请求范围" | 客户端返回当前根目录集合 |
| `notifications/roots/list_changed` | "用户更改了范围" | 客户端信号根目录集合已变更 |
| Elicitation（引出） | "调用中途询问用户" | 服务器发起的结构化用户输入请求 |
| `elicitation/create` | "那个方法" | 用于引出请求的 JSON-RPC 方法 |
| Form Mode（表单模式） | "Schema 驱动的表单" | 扁平 JSON Schema 在客户端 UI 中渲染为表单 |
| URL Mode（URL 模式） | "浏览器重定向" | SEP-1036 实验性；打开 URL 并等待 |
| `accept` / `decline` / `cancel` | "用户响应结果" | 服务器处理的三个分支 |
| Disambiguation（消歧） | "选一个" | 工具有 N 个候选时的常见引出用例 |
| Flat Form（扁平表单） | "仅顶层属性" | 引出 Schema 不能嵌套 |

## 延伸阅读

- [MCP — Client roots spec](https://modelcontextprotocol.io/specification/draft/client/roots) — 规范性根目录参考
- [MCP — Client elicitation spec](https://modelcontextprotocol.io/specification/draft/client/elicitation) — 规范性引出参考
- [Cisco — What's new in MCP elicitation, structured content, OAuth enhancements](https://blogs.cisco.com/developer/whats-new-in-mcp-elicitation-structured-content-and-oauth-enhancements) — 2025-11-25 新增内容演练
- [MCP — GitHub SEP-1036](https://github.com/modelcontextprotocol/modelcontextprotocol) — URL 模式引出提案（实验性，有漂移风险）
- [The New Stack — How elicitation brings human-in-the-loop to AI tools](https://thenewstack.io/how-elicitation-in-mcp-brings-human-in-the-loop-to-ai-tools/) — UX 演练