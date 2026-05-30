# 构建 MCP 服务器 — Python + TypeScript SDK

> 大多数 MCP 教程只演示 stdio hello-world。一个真正的服务器需要暴露 tools 加 resources 加 prompts、处理能力协商、发出结构化错误，并且在不同 SDK 间行为一致。本课从零到一构建一个笔记服务器：stdio 传输层（标准库）、JSON-RPC 分发、三个服务端原语，以及一种纯函数风格，可直接迁移到 Python SDK 的 FastMCP 或 TypeScript SDK。

**类型：** Build
**语言：** Python（stdlib，stdio MCP 服务器）
**前置课程：** Phase 13 · 06（MCP 基础）
**时间：** ~75 分钟

## 学习目标

- 实现 `initialize`、`tools/list`、`tools/call`、`resources/list`、`resources/read`、`prompts/list` 和 `prompts/get` 方法。
- 编写一个从 stdin 读取 JSON-RPC 消息、向 stdout 写入响应的分发循环。
- 按 JSON-RPC 2.0 规范和 MCP 的附加错误码发出结构化错误响应。
- 将标准库实现迁移到 FastMCP（Python SDK）或 TypeScript SDK，无需重写工具逻辑。

## 问题

在使用远程传输层（Phase 13 · 09）或授权层（Phase 13 · 16）之前，你需要一个干净的本地服务器。本地意味着 stdio：服务器由客户端作为子进程启动，消息通过 stdin/stdout 以换行符分隔传输。

2025-11-25 规范规定 stdio 消息编码为 JSON 对象，以显式 `\n` 分隔。这里没有 SSE；SSE 是旧的远程模式，将在 2026 年中期移除（Atlassian 的 Rovo MCP 服务器于 2026 年 6 月 30 日废弃了它；Keboola 于 2026 年 4 月 1 日废弃）。对于 stdio，一行一个 JSON 对象就是全部线路格式。

笔记服务器是一个好的选型，因为它涵盖了所有三个服务端原语。工具执行变更操作（`notes_create`）。资源暴露数据（`notes://{id}`）。提示模板（`review_note`）。本课的模式可以泛化到任何领域。

## 核心概念

### 分发循环

```
loop:
  line = stdin.readline()
  msg = json.loads(line)
  if has id:
    handle request -> write response
  else:
    handle notification -> no response
```

三条规则：

- 不要向 stdout 输出非 JSON-RPC 信封的任何内容。调试日志输出到 stderr。
- 每个请求**必须**匹配一个带有相同 `id` 的响应。
- 通知**不得**响应。

### 实现 `initialize`

```python
def initialize(params):
    return {
        "protocolVersion": "2025-11-25",
        "capabilities": {
            "tools": {"listChanged": True},
            "resources": {"listChanged": True, "subscribe": False},
            "prompts": {"listChanged": False},
        },
        "serverInfo": {"name": "notes", "version": "1.0.0"},
    }
```

只声明你支持的。客户端依赖能力集来控制功能。

### 实现 `tools/list` 和 `tools/call`

`tools/list` 返回 `{tools: [...]}`，每个条目包含 `name`、`description`、`inputSchema`。`tools/call` 接收 `{name, arguments}` 并返回 `{content: [blocks], isError: bool}`。

内容块是有类型的。最常见的：

```json
{"type": "text", "text": "Found 2 notes"}
{"type": "resource", "resource": {"uri": "notes://14", "text": "..."}}
{"type": "image", "data": "<base64>", "mimeType": "image/png"}
```

工具错误有两种形式。协议级错误（未知方法、参数错误）是 JSON-RPC 错误。工具级错误（调用合法但工具执行失败）返回为 `{content: [...], isError: true}`。这让模型能在上下文中看到失败信息。

### 实现资源

资源在设计上是只读的。`resources/list` 返回清单；`resources/read` 返回内容。URI 可以是 `file://...`、`http://...` 或自定义 scheme 如 `notes://`。

当你将数据暴露为资源而非工具时：

- 模型不会"调用"它；客户端可以在用户请求时将其注入上下文。
- 订阅让服务器在资源变更时推送更新（Phase 13 · 10）。
- Phase 13 · 14 将其扩展为 `ui://` 交互式资源。

### 实现提示模板

提示模板是带命名参数的模板。宿主将其作为斜杠命令呈现。一个 `review_note` 提示可能接收一个 `note_id` 参数，并生成一个客户端可以喂给其模型的多消息提示模板。

### Stdio 传输层细节

- 换行符分隔的 JSON。没有长度前缀帧。
- 不要缓冲。每次写入后调用 `sys.stdout.flush()`。
- 客户端控制生命周期。当 stdin 关闭（EOF）时，干净退出。
- 不要静默处理 SIGPIPE；记录日志并退出。

### 注解（Annotations）

每个工具可以携带 `annotations` 来描述安全属性：

- `readOnlyHint: true` — 纯读，可安全重试。
- `destructiveHint: true` — 不可逆的副作用；客户端应确认。
- `idempotentHint: true` — 相同输入产生相同输出。
- `openWorldHint: true` — 与外部系统交互。

客户端使用这些来决定 UX（确认对话框、状态指示器）和路由（Phase 13 · 17）。

### 毕业路径

`code/main.py` 中的标准库服务器约 180 行。FastMCP（Python）将相同的逻辑压缩为装饰器风格：

```python
from fastmcp import FastMCP
app = FastMCP("notes")

@app.tool()
def notes_search(query: str, limit: int = 10) -> list[dict]:
    ...
```

TypeScript SDK 有等价的形式。当你准备好时可以无缝迁移；概念（能力、分发、内容块）是相同的。

## 使用方法

`code/main.py` 是一个完整的基于 stdio 的笔记 MCP 服务器，仅使用标准库。它处理 `initialize`、`tools/list`、三个工具的 `tools/call`（`notes_list`、`notes_search`、`notes_create`）、每条笔记的 `resources/list` 和 `resources/read`、以及一个 `review_note` 提示模板。你可以通过管道发送 JSON-RPC 消息来驱动它：

```
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python main.py
```

关注要点：

- 分发器是一个以方法名为键的 `dict[str, Callable]`。
- 每个工具执行器返回内容块列表，而不是裸字符串。
- 当执行器抛出异常时设置 `isError: true`。

## 交付产出

本课产出 `outputs/skill-mcp-server-scaffolder.md`。给定一个领域（笔记、工单、文件、数据库），该技能会搭建一个具有正确 tools / resources / prompts 分离和 SDK 毕业路径的 MCP 服务器骨架。

## 练习

1. 运行 `code/main.py`，用手工构建的 JSON-RPC 消息驱动它。先调用 `notes_create`，然后 `resources/read` 来获取新笔记。

2. 添加一个 `notes_delete` 工具，带 `annotations: {destructiveHint: true}`。验证客户端会弹出确认对话框（需要真实宿主；Claude Desktop 可以）。

3. 实现 `resources/subscribe`，使服务器在笔记修改时推送 `notifications/resources/updated`。添加一个 keepalive 任务。

4. 将服务器移植到 FastMCP。Python 文件应缩减到 80 行以下。线路行为必须相同；用相同的 JSON-RPC 测试脚手架验证。

5. 阅读规范的 `server/tools` 部分，找出本课服务器未实现的一个工具定义字段。（提示：有好几个；选一个加上。）

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| MCP Server（MCP 服务器） | "暴露工具的东西" | 通过 stdio 或 HTTP 通信的 MCP JSON-RPC 进程 |
| Stdio Transport（Stdio 传输层） | "子进程模型" | 服务器由客户端启动；通过 stdin/stdout 通信 |
| Dispatcher（分发器） | "方法路由器" | JSON-RPC 方法名到处理函数的映射 |
| Content Block（内容块） | "工具结果块" | 工具响应 `content` 数组中的类型化元素 |
| `isError` | "工具级失败" | 信号表示工具失败；与 JSON-RPC 错误区分 |
| Annotations（注解） | "安全提示" | readOnly / destructive / idempotent / openWorld 标志 |
| FastMCP | "Python SDK" | 基于装饰器的 MCP 协议上层框架 |
| Resource URI（资源 URI） | "可寻址数据" | 标识资源的 `file://`、`db://` 或自定义 scheme |
| Prompt Template（提示模板） | "斜杠命令简介" | 服务器提供的带参数槽的宿主 UI 模板 |
| Capability Declaration（能力声明） | "功能开关" | 在 `initialize` 中声明的每个原语的标志 |

## 延伸阅读

- [Model Context Protocol — Python SDK](https://github.com/modelcontextprotocol/python-sdk) — 参考 Python 实现
- [Model Context Protocol — TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) — 并行 TS 实现
- [FastMCP — server framework](https://gofastmcp.com/) — MCP 服务器的装饰器风格 Python API
- [MCP — Quickstart server guide](https://modelcontextprotocol.io/quickstart/server) — 使用任一 SDK 的端到端教程
- [MCP — Server tools spec](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) — tools/* 消息的完整参考