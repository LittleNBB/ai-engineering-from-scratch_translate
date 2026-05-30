# MCP 网关与注册表 — 企业控制平面

> 企业不能让每个开发者随意安装 MCP 服务器。网关集中化认证、RBAC、审计、速率限制、缓存和工具投毒检测，然后将合并的工具面暴露为单个 MCP 端点。官方 MCP 注册表（Anthropic + GitHub + PulseMCP + Microsoft，命名空间验证）是规范性的上游。本课说明网关的位置，走一遍最简实现，并调研 2026 年厂商格局。

**类型：** Learn
**语言：** Python（stdlib，最简网关）
**前置课程：** Phase 13 · 15（工具投毒）、Phase 13 · 16（OAuth 2.1）
**时间：** ~45 分钟

## 学习目标

- 解释 MCP 网关的位置（在 MCP 客户端和多个后端 MCP 服务器之间）。
- 实现网关的五项职责：认证、RBAC、审计、速率限制、策略。
- 在网关层强制执行固定工具 hash 清单。
- 区分官方 MCP 注册表和元注册表（Glama、MCPMarket、MCP.so、Smithery、LobeHub）。

## 问题

一家财富 500 强企业有 30 个已批准的 MCP 服务器、5000 名开发者、合规和审计要求，以及一个需要集中策略的安全团队。让每个开发者在 IDE 中随意安装服务器是不可接受的。

网关模式：

1. 网关作为单个 Streamable HTTP 端点运行，开发者连接它。
2. 网关持有每个后端 MCP 服务器的凭证。
3. 每个开发者请求都通过网关自己的 OAuth 进行认证和范围限定。
4. 网关将调用路由到后端服务器，应用策略。
5. 所有调用记录审计。

Cloudflare MCP Portals、Kong AI Gateway、IBM ContextForge、MintMCP、TrueFoundry、Envoy AI Gateway — 都在 2025-2026 年发布了网关或网关功能。

与此同时，官方 MCP 注册表作为规范性上游启动：经过筛选、命名空间验证、反向 DNS 命名的服务器，网关可以从中拉取。元注册表（Glama、MCPMarket、MCP.so、Smithery、LobeHub）跨多个来源聚合服务器。

## 核心概念

### 网关的五项职责

1. **认证。** OAuth 2.1 识别开发者；映射到用户角色。
2. **RBAC。** 每用户策略：哪些服务器、哪些工具、哪些范围。
3. **审计。** 每次调用记录谁、什么、何时、结果。
4. **速率限制。** 每用户/每工具/每服务器上限防止滥用。
5. **策略。** 拒绝投毒描述、强制二元法则、脱敏 PII。

### 网关作为单端点

对开发者来说，网关看起来像一个 MCP 服务器。内部它路由到 N 个后端。会话 id（Phase 13 · 09）在边界处重写。

### 凭证保管

开发者永远看不到后端 token。网关持有它们（或代理到持有它们的身份提供商）。一个在网关上有 `notes:read` 的开发者可以通过网关自己的后端凭证传递性地访问笔记 MCP 服务器 — 但仅在绑定传递访问的策略下。

### 网关层的工具 hash 固定

网关持有已批准工具描述的清单（SHA256 hash）。在发现时，它获取每个后端的 `tools/list`，将 hash 与清单比较，移除描述已变更的任何工具。这是 Phase 13 · 15 中 rug pull 防御的集中化应用。

### 策略即代码

高级网关用 OPA/Rego、Kyverno 或 Styra 表达策略。像"用户 `alice` 只能在组织 `acme` 的仓库上调用 `github.open_pr`"这样的规则被声明式编码。简单网关使用手写 Python。两种形式都有效。

### 会话感知路由

当用户的会话包含多个服务器的混合时，网关进行多路复用：开发者的单个 MCP 会话持有 N 个后端会话，每个服务器一个。来自任何后端的通知通过网关路由到开发者的会话。

### 命名空间合并

网关合并所有后端的工具命名空间，通常在冲突时加前缀。`github.open_pr`、`notes.search`。这使路由无歧义。

### 注册表

- **官方 MCP 注册表（`registry.modelcontextprotocol.io`）。** 在 Anthropic、GitHub、PulseMCP、Microsoft 管理下启动。命名空间验证（反向 DNS：`io.github.user/server`）。预筛选基本质量。
- **Glama。** 以搜索为中心的元注册表，聚合多个来源。
- **MCPMarket。** 商业导向的目录，有厂商列表。
- **MCP.so。** 社区目录；开放提交。
- **Smithery。** 包管理器风格的安装流程。
- **LobeHub。** 在其 LobeChat 应用中的 UI 集成注册表。

企业网关默认从官方注册表拉取，允许管理员从元注册表中筛选添加，拒绝任何未固定的内容。

### 反向 DNS 命名

官方注册表要求公开服务器使用反向 DNS 名称：`io.github.alice/notes`。命名空间防止抢注，使信任委托更清晰。

### 厂商调研，2026 年 4 月

| 厂商 | 优势 |
|------|------|
| Cloudflare MCP Portals | 边缘托管；OAuth 集成；免费层 |
| Kong AI Gateway | K8s 原生；细粒度策略；日志输出到 OpenTelemetry |
| IBM ContextForge | 企业 IAM；合规；审计导出 |
| TrueFoundry | DevOps 倾向；指标优先 |
| MintMCP | 开发者平台导向 |
| Envoy AI Gateway | 开源；可自定义过滤器 |

Phase 17（生产基础设施）更深入地讲解网关运营。

## 使用方法

`code/main.py` 用约 150 行代码提供了一个最简网关：通过假 Bearer token 认证用户，持有每用户 RBAC 策略，将请求路由到两个后端 MCP 服务器，将每次调用写入审计日志，强制速率限制，拒绝描述 hash 不匹配固定清单的任何后端工具。

关注要点：

- `RBAC` 字典以 `user_id` 为键，包含允许的 `server_tool` 条目。
- `AUDIT_LOG` 是一个追加式事件列表。
- 速率限制使用每用户令牌桶。
- 固定清单是 `server::tool -> hash` 的字典。

## 交付产出

本课产出 `outputs/skill-gateway-bootstrap.md`。给定一个企业 MCP 计划（用户、后端、合规），该技能生成网关配置规范。

## 练习

1. 运行 `code/main.py`。以允许的用户发起调用；然后以不允许的用户；然后触发速率限制超额的突发。验证所有三个流程。

2. 添加一个策略，在返回客户端前从结果中脱敏 PII。用简单的正则匹配 SSN 形状的字符串；注意其不足（邮箱、电话号码）。

3. 扩展审计日志以发出 OpenTelemetry GenAI span。Phase 13 · 20 讲解具体属性。

4. 为一个 50 人开发团队设计 RBAC 策略，有五个后端（notes、github、postgres、jira、slack）。谁对每个有只读权限？谁有写权限？

5. 从头到尾阅读 Cloudflare 的企业 MCP 文章。找出 Cloudflare 提供的、这个标准库网关没有的一个功能。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Gateway（网关） | "MCP 代理" | 客户端和后端之间的集中化服务器 |
| Credential Vaulting（凭证保管） | "后端 token 留在服务端" | 开发者永远看不到上游 token |
| Session-aware Routing（会话感知路由） | "多后端会话" | 网关为每个开发者会话多路复用 N 个后端会话 |
| Tool-hash Pinning（工具 hash 固定） | "已批准清单" | 每个已批准工具描述的 SHA256；集中阻止 rug pull |
| RBAC | "每用户策略" | 工具和服务器的基于角色的访问控制 |
| Policy-as-code（策略即代码） | "声明式规则" | 在网关强制执行的 OPA/Rego、Kyverno、Styra 策略 |
| Audit Log（审计日志） | "谁、什么、何时" | 用于合规的追加式事件日志 |
| Rate Limit（速率限制） | "每用户令牌桶" | 每分钟上限防止滥用 |
| Official MCP Registry（官方 MCP 注册表） | "规范性上游" | `registry.modelcontextprotocol.io`，命名空间验证 |
| Reverse-DNS Naming（反向 DNS 命名） | "注册表命名空间" | `io.github.user/server` 约定 |

## 延伸阅读

- [Official MCP Registry](https://registry.modelcontextprotocol.io/) — 规范性上游，命名空间验证
- [Cloudflare — Enterprise MCP](https://blog.cloudflare.com/enterprise-mcp/) — 带 OAuth 和策略的网关模式
- [agentic-community — MCP gateway registry](https://github.com/agentic-community/mcp-gateway-registry) — 开源参考网关
- [TrueFoundry — What is an MCP gateway?](https://www.truefoundry.com/blog/what-is-mcp-gateway) — 功能比较文章
- [IBM — MCP context forge](https://github.com/IBM/mcp-context-forge) — IBM 的企业网关