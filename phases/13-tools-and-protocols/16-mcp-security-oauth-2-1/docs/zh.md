# MCP 安全（二） — OAuth 2.1、资源指示器、增量范围

> 远程 MCP 服务器需要授权，而不仅仅是认证。2025-11-25 规范与 OAuth 2.1 + PKCE + 资源指示器（RFC 8707）+ 受保护资源元数据（RFC 9728）保持一致。SEP-835 添加了增量范围同意，在 403 WWW-Authenticate 时进行提升授权。本课将提升流程实现为状态机，让你看到每一跳。

**类型：** Build
**语言：** Python（stdlib，OAuth 状态机模拟器）
**前置课程：** Phase 13 · 09（传输层）、Phase 13 · 15（安全一）
**时间：** ~75 分钟

## 学习目标

- 区分资源服务器和授权服务器的职责。
- 走完 PKCE 保护的 OAuth 2.1 授权码流程。
- 使用 `resource`（RFC 8707）和受保护资源元数据（RFC 9728）防止混淆代理攻击。
- 实现提升授权：服务器以 403 和 WWW-Authenticate 响应，请求更高范围；客户端重新提示用户同意并重试。

## 问题

早期 MCP（2025 年之前）使用临时 API 密钥甚至无认证来发布远程服务器。2025-11-25 规范通过完整的 OAuth 2.1 配置文件弥补了这个差距。

三个现实需求：

- **普通远程服务器。** 用户安装一个访问其 Notion / GitHub / Gmail 的远程 MCP 服务器。OAuth 2.1 加 PKCE 是正确的形式。
- **范围提升。** 一个被授予 `notes:read` 的笔记服务器后来可能需要 `notes:write` 来执行特定动作。不需要重新走完整流程，提升（SEP-835）请求额外范围。
- **防止混淆代理。** 客户端持有一个针对服务器 A 的 token。服务器 A 是恶意的，尝试将 token 呈给服务器 B。资源指示器（RFC 8707）将 token 固定到其预期受众。

OAuth 2.1 不是新的。新的是 MCP 的配置文件：特定的必需流程（仅授权码 + PKCE；无隐式、默认无客户端凭证）、每个 token 请求都必须使用资源指示器、以及发布的受保护资源元数据让客户端知道去哪里。

## 核心概念

### 角色

- **客户端。** MCP 客户端（Claude Desktop、Cursor 等）。
- **资源服务器。** MCP 服务器（笔记、GitHub、Postgres 等）。
- **授权服务器。** 颁发 token。可以是与资源服务器相同的服务，也可以是独立的 IdP（Auth0、Keycloak、Cognito）。

在 MCP 的配置文件中，资源和授权服务器**可以**是同一主机，但**应该**通过 URL 区分。

### 授权码 + PKCE

流程：

1. 客户端生成 `code_verifier`（随机）和 `code_challenge`（SHA256）。
2. 客户端将用户重定向到 `/authorize?response_type=code&client_id=...&redirect_uri=...&scope=notes:read&code_challenge=...&resource=https://notes.example.com`。
3. 用户同意。授权服务器重定向到 `redirect_uri?code=...`。
4. 客户端 POST 到 `/token?grant_type=authorization_code&code=...&code_verifier=...&resource=...`。
5. 授权服务器验证 verifier 的 hash 与存储的 challenge 匹配，颁发 access token。
6. 客户端使用 token：每个请求到资源服务器都带 `Authorization: Bearer ...`。

PKCE 防止授权码拦截攻击。资源指示器防止 token 在其他地方有效。

### 受保护资源元数据（RFC 9728）

资源服务器发布 `.well-known/oauth-protected-resource` 文档：

```json
{
  "resource": "https://notes.example.com",
  "authorization_servers": ["https://auth.example.com"],
  "scopes_supported": ["notes:read", "notes:write", "notes:delete"]
}
```

客户端从资源服务器发现授权服务器。减少配置 — 客户端只需要资源 URL。

### 资源指示器（RFC 8707）

token 请求中的 `resource` 参数将 token 固定到其预期受众。颁发的 token 包含 `aud: "https://notes.example.com"`。另一个接收到此 token 的 MCP 服务器检查 `aud` 并拒绝它。

### 范围模型

范围是空格分隔的字符串。常见 MCP 约定：

- `notes:read`、`notes:write`、`notes:delete`
- `admin:*` 用于管理能力（谨慎使用）
- `profile:read` 用于身份

范围选择应遵循最小权限：请求你现在需要的，需要更多时再提升。

### 提升授权（SEP-835）

用户授予了 `notes:read`。他们后来要求 Agent 删除一条笔记。服务器响应：

```
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
    scope="notes:delete", resource="https://notes.example.com"
```

客户端看到 insufficient_scope 错误，提示用户对额外范围的同意对话框，为其执行一个迷你 OAuth 流程，用新 token 重试请求。

### Token 受众验证

每个请求：服务器检查 `token.aud == self.resource_url`。不匹配 = 401。这阻止了跨服务器 token 复用。

### 短效 token 和轮换

Access token **应该**是短效的（默认 1 小时）。Refresh token 每次刷新时轮换。客户端在后台处理静默刷新。

### 不允许 token 透传

采样服务器（Phase 13 · 11）**不得**将客户端的 token 传递给其他服务。采样请求就是边界。

### 防止混淆代理

Token 绑定到 `aud`。客户端绑定到 `client_id`。每个请求都对两者进行验证。规范明确禁止了旧的"传递 token"模式，这在 pre-MCP 的远程工具生态系统中很常见。

### 客户端 ID 发现

每个 MCP 客户端在固定 URL 发布其元数据。授权服务器可以获取客户端的元数据文档来发现重定向 URI 和联系信息。这消除了手动客户端注册。

### 网关与 OAuth

Phase 13 · 17 展示企业网关如何处理 OAuth：网关持有上游服务器的凭证，给客户端的 token 是网关颁发的，上游 token 永远不离开网关。这翻转了信任模型 — 用户只对网关认证一次；网关处理 N 个服务器的授权。

## 使用方法

`code/main.py` 将完整的 OAuth 2.1 提升流程模拟为状态机。它实现：

- PKCE code-verifier / challenge 生成。
- 带资源指示器的授权码流程。
- 受保护资源元数据端点。
- 带受众检查的 token 验证。
- `insufficient_scope` 时的提升。

本课没有 HTTP 服务器；状态机在内存中运行，让你追踪每一跳。Phase 13 · 17 的网关课程将其连接到实际传输层。

## 交付产出

本课产出 `outputs/skill-oauth-scope-planner.md`。给定一个带工具的远程 MCP 服务器，该技能设计范围集、固定规则和提升策略。

## 练习

1. 运行 `code/main.py`。追踪两范围提升流程。注意提升时哪些跳会重复。

2. 添加 refresh token 轮换：每次刷新颁发新的 refresh token 并使旧的失效。模拟轮换后被盗的 refresh token 被使用，确认它失败。

3. 使用标准库 http.server 将受保护资源元数据端点实现为真实的 HTTP 响应。镜像 Lesson 09 的 /mcp 端点。

4. 为一个 GitHub MCP 服务器设计范围层次：read repo、write PR、approve PR、merge PR、admin。每级之间使用提升。

5. 阅读 RFC 8707 和 RFC 9728。找出 9728 中 MCP 与 RFC 示例用法不同的那个字段。（提示：它与 `scopes_supported` 有关。）

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| OAuth 2.1 | "现代 OAuth" | 强制 PKCE 并禁止隐式流程的合并 RFC |
| PKCE | "持有证明" | Code verifier + challenge 击败授权码拦截 |
| Resource Indicator（资源指示器） | "Token 受众" | RFC 8707 `resource` 参数将 token 固定到一台服务器 |
| Protected-resource Metadata（受保护资源元数据） | "发现文档" | RFC 9728 `.well-known/oauth-protected-resource` |
| Step-up Authorization（提升授权） | "增量同意" | SEP-835 按需添加范围的流程 |
| `insufficient_scope` | "403 加 WWW-Authenticate" | 服务器信号：为更大范围重新同意 |
| Confused Deputy（混淆代理） | "跨服务 token 复用" | 受信持有者不当地转发 token 的攻击 |
| Short-lived Token（短效 token） | "Access token TTL" | 快速过期的 Bearer；refresh token 续期 |
| Scope Hierarchy（范围层次） | "最小权限栈" | 带逐级提升的渐进范围集 |
| Client ID Metadata（客户端 ID 元数据） | "客户端发现文档" | 客户端发布自己 OAuth 元数据的 URL |

## 延伸阅读

- [MCP — Authorization spec](https://modelcontextprotocol.io/specification/draft/basic/authorization) — 规范性 MCP OAuth 配置文件
- [den.dev — MCP November authorization spec](https://den.dev/blog/mcp-november-authorization-spec/) — 2025-11-25 变更演练
- [RFC 8707 — Resource indicators for OAuth 2.0](https://datatracker.ietf.org/doc/html/rfc8707) — 受众固定的 RFC
- [RFC 9728 — OAuth 2.0 protected resource metadata](https://datatracker.ietf.org/doc/html/rfc9728) — 发现文档 RFC
- [Aembit — MCP OAuth 2.1, PKCE and the future of AI authorization](https://aembit.io/blog/mcp-oauth-2-1-pkce-and-the-future-of-ai-authorization/) — 实际提升流程演练