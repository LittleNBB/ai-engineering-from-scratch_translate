# 生产环境 MCP 认证 — DCR、JWKS 轮换、受众固定 Token

> Lesson 16 在内存中搭建了 OAuth 2.1 状态机。到 2026 年，你部署到真实组织的每个 MCP 服务器都处于生产认证之后：动态客户端注册（RFC 7591）、授权服务器元数据发现（RFC 8414）、不会在凌晨三点 token 验证时失效的 JWKS 轮换、以及拒绝混淆代理重用的受众固定 token。本课通过 iii 原语将所有这些串联起来 — `iii.registerTrigger` 用于 HTTP 和 cron、`iii.registerFunction` 用于认证逻辑、`state::set/get` 用于缓存的密钥 — 使认证面可观察、可重启、可重放，就像引擎中的每个其他工作负载一样。

**类型：** Build
**语言：** Python（stdlib，iii 原语在课程环境中被模拟）
**前置课程：** Phase 13 · 16（OAuth 2.1 状态机）、Phase 13 · 17（网关）
**时间：** ~90 分钟

## 学习目标

- 通过 RFC 8414 元数据发现授权服务器并验证契约。
- 实现 RFC 7591 动态客户端注册，使 MCP 客户端无需管理员干预即可注册。
- 使用 cron 触发器缓存和轮换 JWKS 密钥，使签名验证在密钥轮换时不受影响。
- 使用 RFC 8707 资源指示器将 token 固定到单个 MCP 资源，拒绝混淆代理重用。
- 将每个端点和后台任务串联为 iii 原语 — HTTP 触发器、cron 触发器、命名函数和 `state::*` 读取 — 使单次重启即可重建认证面。
- 阅读 IdP 能力矩阵，在 IdP 无法满足 MCP 认证配置文件时拒绝部署。

## 问题

Lesson 16 的模拟器在内存中运行 OAuth 2.1。生产环境有三个纯内存模拟器看不到的操作差距。

第一个差距是注册。一个真实组织运行数百个 MCP 服务器和数千个 MCP 客户端。运维人员不会手动将每个 Cursor 用户注册为 OAuth 客户端。RFC 7591 动态客户端注册让客户端可以向授权服务器 `POST /register`，当场获得 `client_id`（以及可选的 `client_secret`）。服务器在其 RFC 8414 元数据中发布 `registration_endpoint`；客户端无需带外配置即可发现它。

第二个差距是密钥轮换。JWT 验证依赖授权服务器的签名密钥，以 JSON Web Key Set（JWKS）形式发布。授权服务器按计划轮换这些密钥（通常每小时，有时在事件响应下更快）。一个在启动时获取一次 JWKS 的 MCP 服务器在轮换窗口之前验证正常 — 然后每个请求都会失败直到重启。生产环境将 JWKS 作为缓存值串联一个刷新任务，在之前的密钥过期前覆写缓存，加上缓存未命中时的回退获取，以处理比缓存更新的密钥签名的 token 到达的情况。

第三个差距是受众绑定。Lesson 16 介绍了 RFC 8707 资源指示器。在生产中，该指示器成为每个请求的硬性声明检查。MCP 服务器将 `token.aud` 与其自己的规范资源 URL 进行比较，不匹配时以 HTTP 401 拒绝。这是防止上游 MCP 服务器（或持有针对一台服务器的 token 的恶意客户端）在同一信任网格中对另一台服务器重放该 token 的唯一防御。

本课将每一个差距视为一个 iii 原语。元数据文档是一个 HTTP 触发器，返回函数的输出。JWKS 轮换是一个 cron 触发器，调用 `auth::rotate-jwks`，后者写入 `state::set("auth/jwks/<issuer>", ...)`。JWT 验证是一个函数，其他组件通过 `iii.trigger("auth::validate-jwt", token)` 调用。MCP 服务器本身只是另一个 HTTP 触发器，在分发前调用验证。重启引擎：触发器注册表重建；状态存活；认证面无需手动调和即可运行。

## 核心概念

### RFC 8414 — OAuth 授权服务器元数据

`/.well-known/oauth-authorization-server` 处的文档描述了客户端需要的一切：

```json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/authorize",
  "token_endpoint": "https://auth.example.com/token",
  "jwks_uri": "https://auth.example.com/.well-known/jwks.json",
  "registration_endpoint": "https://auth.example.com/register",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "code_challenge_methods_supported": ["S256"],
  "scopes_supported": ["mcp:tools.read", "mcp:tools.invoke"],
  "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"]
}
```

给定 MCP 资源 URL 的客户端链接发现：RFC 9728 的 `oauth-protected-resource`（资源服务器的文档）命名颁发者，然后 `oauth-authorization-server`（本 RFC）命名每个端点。客户端永远不硬编码授权 URL。

你在信任 IdP 用于 MCP 之前验证的契约：

- `code_challenge_methods_supported` 包含 `S256`（RFC 7636 的 PKCE）。
- `grant_types_supported` 包含 `authorization_code` 并拒绝 `password` 和 `implicit`。
- `registration_endpoint` 存在（RFC 7591 支持）。
- `response_types_supported` 对于 OAuth 2.1 恰好是 `["code"]`。

如果缺少任何一项，MCP 服务器拒绝对此 IdP 部署。部署清单错了，不是代码。

### RFC 9728（回顾） — 受保护资源元数据

Lesson 16 覆盖了 RFC 9728。生产中的增量：此文档是客户端查找*此*MCP 服务器信任的授权服务器的唯一位置。单个 MCP 服务器可能接受来自多个 IdP 的 token（一个给员工，一个给合作伙伴）。RFC 9728 声明该集合；RFC 8414 记录每个 IdP 支持什么。

```json
{
  "resource": "https://notes.example.com",
  "authorization_servers": ["https://auth.example.com", "https://partners.example.com"],
  "scopes_supported": ["mcp:tools.invoke"],
  "bearer_methods_supported": ["header"],
  "resource_documentation": "https://notes.example.com/docs"
}
```

### RFC 7591 — 动态客户端注册

没有 DCR，每个 MCP 客户端（Cursor、Claude Desktop、自定义 Agent）都需要与 IdP 管理员进行带外交换。有了 DCR，客户端发送：

```json
POST /register
Content-Type: application/json

{
  "redirect_uris": ["http://127.0.0.1:7333/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "none",
  "scope": "mcp:tools.invoke",
  "client_name": "Cursor",
  "software_id": "com.cursor.cursor",
  "software_version": "0.42.0"
}
```

服务器回复 `client_id` 和一个 `registration_access_token` 用于后续更新：

```json
{
  "client_id": "c_3e7f1a",
  "client_id_issued_at": 1769472000,
  "redirect_uris": ["http://127.0.0.1:7333/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "registration_access_token": "regt_b2...",
  "registration_client_uri": "https://auth.example.com/register/c_3e7f1a"
}
```

`token_endpoint_auth_method: none` 是运行在用户设备上的 MCP 客户端的正确默认值。它们只获得 `client_id` — 没有可被外泄的 `client_secret`。PKCE 提供公共客户端所需的持有证明。

三个生产陷阱：

- 注册端点必须按源 IP 速率限制。否则，恶意行为者可以脚本化数百万个假注册并耗尽 `client_id` 命名空间。iii 使这变得简单：注册 HTTP 触发器在分发到注册器之前调用一个 `auth::rate-limit` 函数。
- 某些企业 IdP 要求 `software_statement`（担保客户端的签名 JWT）。本课的模拟跳过了它；生产环境串联一个验证步骤，拒绝来自非 localhost 重定向 URI 的未签名注册。
- `registration_access_token` 必须以 hash 存储，而非明文。此 token 的泄露意味着攻击者可以重写客户端的重定向 URI。

### RFC 8707（回顾） — 资源指示器

Lesson 16 确立了形式。生产规则：每个 token 请求包含 `resource=<canonical-mcp-url>`，MCP 服务器在每次调用时验证 `token.aud` 匹配其自己的资源 URL。如果 MCP 服务器可通过 `https://notes.example.com/mcp` 访问，规范 URL 是 `https://notes.example.com` — 排除路径组件，以便单个服务器在一个受众下托管多个路径。

### RFC 7636（回顾） — PKCE

PKCE 在 OAuth 2.1 中是强制的。本课的授权码流程始终携带 `code_challenge` 和 `code_verifier`。服务器拒绝任何没有 verifier 或 verifier 的 hash 不匹配存储的 challenge 的 token 请求。

### MCP 规范 2025-11-25 认证配置文件

MCP 规范（2025-11-25）精确规定了 MCP 服务器的授权层必须做什么：

- 发布 `/.well-known/oauth-protected-resource`（RFC 9728）。
- 仅通过 `Authorization: Bearer ...` 接受 token。
- 每个请求验证 `aud`、`iss`、`exp` 和必需的范围。
- 对每个 401 和 403 响应 `WWW-Authenticate`，携带 `Bearer error=...`，包括适用时的 `scope=` 和 `resource=` 参数。
- 拒绝 `aud` 不匹配规范资源的 token。
- 拒绝 `iss` 不在受保护资源元数据 `authorization_servers` 列表中的 token。

OAuth 2.1 草案是基底；RFC 8414/7591/8707/9728 + RFC 7636 是表面；MCP 规范是配置文件。

### IdP 能力矩阵

不是每个 IdP 都支持完整的 MCP 配置文件。下面的矩阵记录了截至 2025-11-25 规范的事实能力声明。它是*部署门控*，不是推荐。

| IdP 类别 | RFC 8414 元数据 | RFC 7591 DCR | RFC 8707 资源 | RFC 7636 S256 PKCE | 说明 |
|---|---|---|---|---|---|
| 自托管（Keycloak） | 是 | 是 | 是（24.x 起） | 是 | 本课 MCP 配置文件的参考 IdP；端到端支持每个 RFC。 |
| 企业 SSO（Microsoft Entra ID） | 是 | 是（高级层） | 是 | 是 | DCR 可用性因租户层而异；部署前在目标租户中验证。 |
| 企业 SSO（Okta） | 是 | 是（Okta CIC / Auth0） | 是 | 是 | DCR 在 Auth0（现 Okta CIC）上可用；经典 Okta 组织需要管理员预注册。 |
| 社交登录 IdP（通用） | 不一定 | 很少 | 很少 | 是 | 大多数社交 IdP 将客户端视为静态合作伙伴；不要依赖 DCR。仅用作身份源，在其上层叠加你自己的 MCP 感知授权服务器。 |
| 自定义/自建 | 取决于 | 取决于 | 取决于 | 取决于 | 如果你自己构建，请构建完整配置文件。跳过上述四个 RFC 中的任何一个都会破坏 MCP 认证契约。 |

部署清单的拒绝规则：如果选定的 IdP 不返回 `registration_endpoint` 且不在 `code_challenge_methods_supported` 中列出 `S256`，MCP 服务器拒绝启动。没有降级模式。

### iii 的 JWKS 轮换模式

生产失败模式是过时的 JWKS 缓存。用 cron 触发器和 `state::*` 缓存解决：

```python
iii.registerTrigger(
    "cron",
    {"schedule": "0 */6 * * *", "name": "auth::jwks-refresh"},
    "auth::rotate-jwks",
)
```

每六小时，cron 触发器调用 `auth::rotate-jwks`，获取 `<issuer>/.well-known/jwks.json` 并写入 `state::set("auth/jwks/<issuer>", {keys, fetched_at})`。验证器从 `state::get` 读取。缓存中缺少 `kid` 的 token 会触发同步 `auth::rotate-jwks` 调用作为回退。这同时处理两种情况：计划轮换（cron）和密钥重叠窗口（同步回退）。

状态形状：

```json
{
  "auth/jwks/https://auth.example.com": {
    "keys": [
      {"kid": "k_2026_03", "kty": "RSA", "n": "...", "e": "AQAB", "alg": "RS256", "use": "sig"},
      {"kid": "k_2026_04", "kty": "RSA", "n": "...", "e": "AQAB", "alg": "RS256", "use": "sig"}
    ],
    "fetched_at": 1772668800
  }
}
```

同时持有两个密钥是稳态。授权服务器通过在退役前一个密钥（`k_2026_03`）之前引入下一个密钥（`k_2026_04`）来进行轮换，因此在旧密钥下颁发的 token 在过期前仍然有效。缓存持有并集；验证器按 `kid` 选择。

### iii 原语串联（本课的核心部分）

五个原语组合成认证面：

```python
# 1. RFC 8414 元数据文档
iii.registerTrigger(
    "http",
    {"path": "/.well-known/oauth-authorization-server", "method": "GET"},
    "auth::serve-asm",
)

# 2. RFC 7591 动态客户端注册
iii.registerTrigger(
    "http",
    {"path": "/register", "method": "POST"},
    "auth::register-client",
)

# 3. JWT 验证作为可调用函数（资源服务器触发它）
iii.registerFunction("auth::validate-jwt", validate_jwt_handler)

# 4. 增量范围的提升颁发（L16 的 SEP-835）
iii.registerFunction("auth::issue-step-up", issue_step_up_handler)

# 5. Cron 驱动的 JWKS 轮换
iii.registerTrigger(
    "cron",
    {"schedule": "0 */6 * * *"},
    "auth::rotate-jwks",
)
iii.registerFunction("auth::rotate-jwks", rotate_jwks_handler)
```

MCP 服务器本身从不直接调用验证。它执行：

```python
result = iii.trigger("auth::validate-jwt", {"token": bearer_token, "resource": self.resource})
if not result["valid"]:
    return {"status": 401, "WWW-Authenticate": result["www_authenticate"]}
```

这个间接层是 iii 的赌注。明天你可以将验证器换成并行查询两个 IdP 的扇出，或者添加 span 发出器，或者缓存正验证。MCP 服务器不会改变。

### 受众绑定的混淆代理演练

服务器 A（`notes.example.com`）和服务器 B（`tasks.example.com`）都向同一个授权服务器注册。服务器 A 被入侵。攻击者获取用户的 notes token 并对服务器 B 重放。

服务器 B 的验证器：

1. 解码 JWT，按 `kid` 获取 JWKS，验证签名。
2. 检查 `iss` 是否在其受保护资源元数据的 `authorization_servers` 中。（通过 — 同一 IdP。）
3. 检查 `aud == "https://tasks.example.com"`。（失败 — token 的 `aud` 是 `https://notes.example.com`。）
4. 返回 401，`WWW-Authenticate: Bearer error="invalid_token", error_description="audience mismatch"`。

受众声明是协议层对此攻击的唯一防御。为了性能而跳过它是最常见的生产错误；验证器必须在每个请求上运行，而不仅仅在会话开始时。

### 失败模式

- **过时的 JWKS。** 密钥轮换后验证器拒绝有效 token。修复方法是上面的 cron+回退模式。永远不要缓存 JWKS 而不配刷新任务。
- **缺少 `aud` 声明。** 某些 IdP 默认在 token 请求中没有 `resource` 时省略 `aud`。验证器必须拒绝缺少 `aud` 的 token，不要将缺失视为通配符。
- **范围升级竞态。** 同一用户的两个并发提升流程可能都成功并产生两个不同范围的 access token。验证器必须使用请求中呈现的 token，而不是查找"用户的当前范围" — 那会创建 TOCTOU 窗口。
- **注册 token 被盗。** 泄露的 `registration_access_token` 让攻击者可以重写重定向 URI。在静态存储时 hash 化；要求客户端在每次更新时呈现明文；在可疑时轮换。
- **`iss` 未固定。** 接受任何 `iss` 的验证器让攻击者可以建立自己的授权服务器，为目标受众注册客户端并颁发 token。受保护资源元数据的 `authorization_servers` 列表就是允许列表；强制执行它。

## 使用方法

`code/main.py` 使用标准库 Python 和一个小型 `iii_mock` 注册表（模拟 `iii.registerFunction`、`iii.registerTrigger`、`iii.trigger` 和 `state::set/get`）走完完整的生产流程。流程：

1. 授权服务器在 `/.well-known/oauth-authorization-server` 发布 RFC 8414 元数据。
2. MCP 客户端调用元数据端点，发现注册端点。
3. MCP 客户端 POST 到 `/register`（RFC 7591）并获得 `client_id`。
4. MCP 客户端运行 PKCE 保护的授权码流程（RFC 7636），带 `resource` 指示器（RFC 8707）。
5. MCP 客户端用 `Authorization: Bearer ...` 调用 MCP 服务器上的工具。
6. MCP 服务器触发 `auth::validate-jwt`，后者从 `state::get` 读取 JWKS。
7. cron 触发器触发 `auth::rotate-jwks`，替换状态中的 JWKS。
8. 下次调用无需重启即可对新密钥验证。
9. 对不同 MCP 资源的混淆代理尝试得到 401 受众不匹配。

此处的模拟 JWT 使用 HS256 共享密钥（以便课程仅在标准库上运行）。生产使用 RS256 或 EdDSA 配合上述 JWKS 模式；验证逻辑在其他方面完全相同。

## 交付产出

本课产出 `outputs/skill-mcp-auth-iii.md`。给定一个 MCP 服务器配置和 IdP 能力集，该技能输出要注册的 iii 原语、JWKS 轮换计划、范围映射、以及当 IdP 不支持完整 RFC 配置文件时要应用的拒绝规则。

## 练习

1. 运行 `code/main.py`。追踪 9 步流程。注意 `state::get` 在 `auth::rotate-jwks` 覆写之前立即返回过时数据的位置，以及下次请求现在如何对新密钥验证。

2. 向受保护资源元数据的 `authorization_servers` 列表添加新 IdP。颁发由新 IdP 签名的 token 并确认验证器接受它。颁发由未列出的 IdP 签名的 token 并确认验证器以 `WWW-Authenticate: Bearer error="invalid_token", error_description="iss not allowed"` 拒绝。

3. 将 `auth::rate-limit` 实现为 iii 函数，并在注册 HTTP 触发器内、注册器运行之前调用它。使用 `state::set("auth/ratelimit/<ip>", ...)` 中的按源 IP 令牌桶。

4. 阅读 RFC 7591 并找出本课 `/register` 处理器未验证的两个字段。添加验证。（提示：`software_statement` 和 `redirect_uris` URI scheme。）

5. 阅读 MCP 规范 2025-11-25 授权部分。找出本课验证器目前未发出的 `WWW-Authenticate` 头上的那个规范性要求。添加它。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| ASM | "OAuth 元数据文档" | RFC 8414 `/.well-known/oauth-authorization-server` JSON |
| DCR | "自助客户端注册" | RFC 7591 `POST /register` 流程 |
| JWKS | "JWT 验证公钥" | JSON Web Key Set，从 `jwks_uri` 获取，按 `kid` 索引 |
| Resource Indicator（资源指示器） | "受众参数" | RFC 8707 `resource` 参数将 token 固定到一台服务器 |
| `aud` 声明 | "受众" | 验证器与规范资源 URL 比较的 JWT 声明 |
| Confused Deputy（混淆代理） | "Token 重放" | 为服务器 A 颁发的 token 被呈给服务器 B 的攻击 |
| `iss` 允许列表 | "受信任的授权服务器" | 受保护资源元数据 `authorization_servers` 中命名的集合 |
| Key Rotation（密钥轮换） | "滚动 JWKS" | 带重叠窗口的签名密钥定期替换 |
| Public Client（公共客户端） | "原生或浏览器客户端" | 无 `client_secret` 的 OAuth 客户端；PKCE 补偿 |
| `WWW-Authenticate` | "401/403 响应头" | 携带 `Bearer error=...` 指令，驱动客户端恢复 |

## 延伸阅读

- [MCP — Authorization spec (2025-11-25)](https://modelcontextprotocol.io/specification/draft/basic/authorization) — 本课实现的 MCP 认证配置文件
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://datatracker.ietf.org/doc/html/rfc8414) — 发现契约
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://datatracker.ietf.org/doc/html/rfc7591) — DCR
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://datatracker.ietf.org/doc/html/rfc7636) — 公共客户端持有证明
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://datatracker.ietf.org/doc/html/rfc8707) — 受众固定
- [RFC 9728 — OAuth 2.0 Protected Resource Metadata](https://datatracker.ietf.org/doc/html/rfc9728) — 资源服务器发现
- [OAuth 2.1 draft](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1) — 合并的 OAuth 基底