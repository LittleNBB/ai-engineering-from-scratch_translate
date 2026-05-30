# MCP Apps — 通过 `ui://` 的交互式 UI 资源

> 纯文本工具输出限制了 Agent 的展示能力。MCP Apps（SEP-1724，2026 年 1 月 26 日正式发布）让工具返回沙箱化的交互式 HTML，在 Claude Desktop、ChatGPT、Cursor、Goose 和 VS Code 中内联渲染。仪表板、表单、地图、3D 场景，全部通过一个扩展实现。本课讲解 `ui://` 资源 scheme、`text/html;profile=mcp-app` MIME、iframe 沙箱 postMessage 协议，以及让服务器渲染 HTML 带来的安全面。

**类型：** Build
**语言：** Python（stdlib，UI 资源发出器）、HTML（示例应用）
**前置课程：** Phase 13 · 07（MCP 服务器）、Phase 13 · 10（资源）
**时间：** ~75 分钟

## 学习目标

- 从工具调用返回 `ui://` 资源并设置正确的 MIME 和元数据。
- 用 `_meta.ui.resourceUri`、`_meta.ui.csp` 和 `_meta.ui.permissions` 声明工具的关联 UI。
- 实现 iframe 沙箱 postMessage JSON-RPC 用于 UI 到宿主的通信。
- 应用 CSP 和 permissions-policy 默认值来防御 UI 发起的攻击。

## 问题

一个 2025 时代的 `visualize_timeline` 工具可以返回"以下是按时间顺序组织的 14 条笔记：……"。这是一段文字。用户实际想要的是交互式时间线。在 MCP Apps 之前，选项是：特定客户端的小组件 API（Claude artifacts、OpenAI Custom GPT HTML），或完全没有 UI。

MCP Apps（SEP-1724，2026 年 1 月 26 日发布）标准化了这个契约。工具结果包含一个 URI 为 `ui://...`、MIME 为 `text/html;profile=mcp-app` 的 `resource`。宿主在带有受限 CSP 的沙箱化 iframe 中渲染它，除非显式授予否则没有网络访问。iframe 内部的 UI 通过一个精简的 postMessage JSON-RPC 方言向宿主发送消息。

每个兼容的客户端（Claude Desktop、ChatGPT、Goose、VS Code）以相同方式渲染同一个 `ui://` 资源。一个服务器、一个 HTML 包、通用 UI。

## 核心概念

### `ui://` 资源 scheme

工具返回：

```json
{
  "content": [
    {"type": "text", "text": "Here is your notes timeline:"},
    {"type": "ui_resource", "uri": "ui://notes/timeline"}
  ],
  "_meta": {
    "ui": {
      "resourceUri": "ui://notes/timeline",
      "csp": {
        "defaultSrc": "'self'",
        "scriptSrc": "'self' 'unsafe-inline'",
        "connectSrc": "'self'"
      },
      "permissions": []
    }
  }
}
```

宿主随后对 `ui://notes/timeline` URI 调用 `resources/read`，得到：

```json
{
  "contents": [{
    "uri": "ui://notes/timeline",
    "mimeType": "text/html;profile=mcp-app",
    "text": "<!doctype html>..."
  }]
}
```

### iframe 沙箱

宿主在沙箱化的 `<iframe>` 中渲染 HTML，具有：

- `sandbox="allow-scripts allow-same-origin"`（或按服务器声明更严格）
- 通过响应头应用服务器声明的 CSP。
- 没有来自宿主 origin 的 cookie 和 localStorage。
- 网络访问受 CSP 中 `connectSrc` 限制。

### postMessage 协议

iframe 通过 `window.postMessage` 与宿主通信。一个精简的 JSON-RPC 2.0 方言：

始终将 `targetOrigin` 固定为对等方的确切 origin，并在接收端验证 `event.origin` 是否在允许列表中，然后再处理任何载荷。永远不要对这个通道的任何一端使用 `"*"` — 载荷中携带工具调用和资源读取。

```js
// iframe 到宿主（固定到宿主 origin）
window.parent.postMessage({
  jsonrpc: "2.0",
  id: 1,
  method: "host.callTool",
  params: { name: "notes_update", arguments: { id: "note-14", title: "..." } }
}, "https://host.example.com");

// 宿主到 iframe（固定到 iframe origin）
iframe.contentWindow.postMessage({
  jsonrpc: "2.0",
  id: 1,
  result: { content: [...] }
}, "https://iframe.example.com");

// 两端的接收器
window.addEventListener("message", (event) => {
  if (event.origin !== "https://expected-peer.example.com") return;
  // 可以安全处理 event.data
});
```

UI 可调用的宿主端方法：

- `host.callTool(name, arguments)` — 调用服务器工具。
- `host.readResource(uri)` — 读取 MCP 资源。
- `host.getPrompt(name, arguments)` — 获取提示模板。
- `host.close()` — 关闭 UI。

每个调用仍然通过 MCP 协议，并继承服务器的权限。

### 权限

`_meta.ui.permissions` 列表请求额外能力：

- `camera` — 访问用户摄像头（用于扫描文档 UI）。
- `microphone` — 语音输入。
- `geolocation` — 位置。
- `network:*` — 比单独 `connectSrc` 允许的更广泛的网络访问。

每个权限是 UI 渲染前用户看到的一个提示。

### 安全风险

iframe 中的 HTML 仍然是 HTML。新的攻击面：

- **通过 UI 的提示注入。** 恶意服务器 UI 可以显示看起来像系统消息的文本来欺骗用户。宿主渲染应该在视觉上区分服务器 UI 和宿主 UI。
- **通过 `connectSrc` 的数据外泄。** 如果 CSP 允许 `connect-src: *`，UI 可以向任何地方发送数据。默认应为严格。
- **点击劫持。** UI 覆盖宿主 chrome。宿主必须防止 z-index 操纵并强制透明度规则。
- **窃取焦点。** UI 获取键盘焦点并捕获下一条消息。宿主必须拦截。

Phase 13 · 15 深入讲解这些作为 MCP 安全的一部分；本课做入门介绍。

### `ui/initialize` 握手

iframe 加载后，通过 postMessage 发送 `ui/initialize`：

```json
{"jsonrpc": "2.0", "id": 0, "method": "ui/initialize",
 "params": {"theme": "dark", "locale": "en-US", "sessionId": "..."}}
```

宿主回复能力和会话 token。UI 在每个后续宿主调用中使用会话 token。

### AppRenderer / AppFrame SDK 原语

ext-apps SDK 提供两个便捷原语：

- `AppRenderer`（服务端）— 封装 React / Vue / Solid 组件，输出带有正确 MIME 和元数据的 `ui://` 资源。
- `AppFrame`（客户端）— 接收资源，挂载 iframe，并中介 postMessage。

你可以使用这些，也可以手写 HTML 和 JSON-RPC。

### 生态状态

MCP Apps 于 2026 年 1 月 26 日发布。截至 2026 年 4 月的客户端支持：

- **Claude Desktop。** 自 2026 年 1 月起完全支持。
- **ChatGPT。** 通过 Apps SDK 完全支持（底层相同的 MCP Apps 协议）。
- **Cursor。** Beta；通过设置启用。
- **VS Code。** 仅 Insider 构建。
- **Goose。** 完全支持。
- **Zed、Windsurf。** 已列入路线图。

生产中的服务器：仪表板、地图可视化、数据表格、图表构建器、沙箱 IDE 预览。

## 使用方法

`code/main.py` 在笔记服务器基础上扩展了一个 `visualize_timeline` 工具，返回 `ui://notes/timeline` 资源，加上一个该 URI 的 `resources/read` 处理器，返回一个小而完整的 HTML 包，包含 SVG 时间线。HTML 使用标准库模板化 — 没有构建系统。postMessage 在 JS 注释中概述，因为标准库无法驱动浏览器。

关注要点：

- 工具响应上的 `_meta.ui` 携带 resourceUri、CSP、permissions。
- HTML 在无网络访问的情况下渲染；所有数据都是内联的。
- JS 通过 `window.parent.postMessage` 调用 `host.callTool`（已文档化但在此标准库演示中是惰性的）。

## 交付产出

本课产出 `outputs/skill-mcp-apps-spec.md`。给定一个受益于交互式 UI 的工具，该技能生成完整的 MCP Apps 契约：`ui://` URI、CSP、权限、postMessage 入口点和安全检查清单。

## 练习

1. 运行 `code/main.py`，检查发出的 HTML。在浏览器中直接打开 HTML；验证 SVG 渲染。然后草绘 UI 用于调用 `host.callTool("notes_update", ...)` 的 postMessage 契约。

2. 收紧 CSP：移除 `'unsafe-inline'` 并使用基于 nonce 的脚本策略。HTML 生成代码需要什么变化？

3. 添加第二个 UI 资源 `ui://notes/editor`，带一个表单用于原地编辑笔记。用户提交时，iframe 调用 `host.callTool("notes_update", ...)`。

4. 审计 UI 的攻击面。恶意服务器可以在哪里注入内容？iframe 沙箱防御了什么，没防御什么？

5. 阅读 SEP-1724 规范，找出这个玩具实现未使用的 MCP Apps SDK 中的一个能力。（提示：组件级状态同步。）

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| MCP Apps | "交互式 UI 资源" | 2026-01-26 发布的 SEP-1724 扩展 |
| `ui://` | "App URI scheme" | UI 包的资源 scheme |
| `text/html;profile=mcp-app` | "那个 MIME" | MCP App HTML 的内容类型 |
| Iframe Sandbox（iframe 沙箱） | "渲染容器" | 带 CSP 和权限的浏览器沙箱化 UI |
| postMessage JSON-RPC | "UI 到宿主的线路" | 用于宿主调用的精简 postMessage 上 JSON-RPC 方言 |
| `_meta.ui` | "工具-UI 绑定" | 将工具结果链接到 UI 资源的元数据 |
| CSP | "Content-Security-Policy" | 声明脚本、网络、样式的允许来源 |
| AppRenderer | "服务端 SDK 原语" | 将框架组件转换为 `ui://` 资源 |
| AppFrame | "客户端 SDK 原语" | 中介 postMessage 的 iframe 挂载助手 |
| `ui/initialize` | "握手" | 从 UI 到宿主的第一个 postMessage |

## 延伸阅读

- [MCP ext-apps — GitHub](https://github.com/modelcontextprotocol/ext-apps) — 参考实现和 SDK
- [MCP Apps specification 2026-01-26](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx) — 正式规范文档
- [MCP — Apps extension overview](https://modelcontextprotocol.io/extensions/apps/overview) — 高级文档
- [MCP blog — MCP Apps launch](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/) — 2026 年 1 月发布文章
- [MCP Apps API reference](https://apps.extensions.modelcontextprotocol.io/api/) — JSDoc 风格 SDK 参考