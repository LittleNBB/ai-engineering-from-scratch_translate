# LLM 路由层 — LiteLLM、OpenRouter、Portkey

> 提供商锁定代价高昂。不同的工具调用工作负载适合不同的模型。路由网关提供统一 API 界面、重试、故障转移、成本追踪和护栏。2026 年有三种主导架构：LiteLLM（开源自托管）、OpenRouter（托管 SaaS）、Portkey（生产级，2026 年 3 月开源）。本课说明决策标准，并走一遍标准库路由网关。

**类型：** Learn
**语言：** Python（stdlib，路由 + 故障转移 + 成本追踪器）
**前置课程：** Phase 13 · 02（Function Calling）、Phase 13 · 17（网关）
**时间：** ~45 分钟

## 学习目标

- 区分自托管、托管和生产级路由选项。
- 实现一个在提供商故障时按定义优先级重试的故障转移链。
- 跨提供商追踪每请求成本和 token 使用量。
- 根据给定的生产约束在 LiteLLM、OpenRouter 和 Portkey 之间做出选择。

## 问题

提供商路由重要的场景：

1. **成本。** Claude Sonnet 的价格是 Haiku 的 3 倍。对于分诊任务，Haiku 就够了；对于综合任务，Sonnet 值得。按请求路由。

2. **故障转移。** OpenAI 有一个糟糕的时段。每个请求都失败。你希望自动回退到 Anthropic 而无需重新部署。

3. **延迟。** 实时聊天 UI 需要快速的首 token 时间。批量摘要生成器不需要。按延迟 SLA 路由。

4. **合规。** EU 用户必须留在 EU 区域。按区域路由。

5. **实验。** 在相同工作负载上 A/B 测试两个模型。按测试桶路由。

为每个集成手动编码所有这些是重复的。路由网关提供一个 OpenAI 兼容的 API 并处理其余一切。

## 核心概念

### OpenAI 兼容代理形式

大家都说 OpenAI 形式。路由网关暴露 `/v1/chat/completions`，接受 OpenAI Schema，内部代理到 Anthropic / Gemini / Cohere / Ollama / 任何提供商。客户端不需要关心。

### 模型别名

你的代码说 `our_smart_model` 而不是 `claude-3-5-sonnet-20251022`。网关将别名映射到真实模型。当 Anthropic 发布 Claude 4 时，你在服务端更改别名；你的代码一行不动。

### 故障转移链

```
primary: openai/gpt-4o
on 5xx: anthropic/claude-3-5-sonnet
on 5xx: google/gemini-1.5-pro
on 5xx: refuse
```

网关在配置中定义这个。重试计数有预算限制，使故障转移级联不会爆炸成本。

### 语义缓存

相同或近似相同的提示命中缓存而非提供商。重复 Agent 循环的节省可达 30% 到 60%。键基于嵌入；近似提示共享缓存槽。

### 护栏

网关级：

- **PII 脱敏。** 发送提示前的正则或 ML 传递。
- **策略违规。** 拒绝包含禁止内容的提示。
- **输出过滤器。** 清理完成内容中的泄漏。

Portkey 和 Kong 都提供有主见的护栏。LiteLLM 将其留为可选。

### 每密钥速率限制

一个 API 密钥 = 一个团队。每密钥预算防止一个团队消耗共享配额。大多数网关支持这个。

### 自托管 vs 托管的权衡

| 因素 | LiteLLM（自托管） | OpenRouter（托管） | Portkey（生产级） |
|------|------------------|-------------------|------------------|
| 代码 | 开源，Python | 托管 SaaS | 开源（2026 年 3 月）+ 托管 |
| 设置 | 部署代理 | 注册 | 两者皆可 |
| 提供商 | 100+ | 300+ | 100+ |
| 计费 | 你自己的密钥 | OpenRouter 积分 | 你自己的密钥 |
| 可观测性 | OpenTelemetry | 仪表板 | 完整 OTel + PII 脱敏 |
| 最适合 | 想要完全控制的团队 | 快速原型 | 需要合规的生产环境 |

当你有 SRE 团队并想要数据主权时，LiteLLM 胜出。当你想要单个订阅且无基础设施时，OpenRouter 胜出。当你需要开箱即用的护栏和合规时，Portkey 胜出。

### 成本追踪

每个请求携带 `provider`、`model`、`input_tokens`、`output_tokens`。乘以每模型每 token 价格（从网关维护的价格表中拉取）。按用户/按团队/按项目聚合。

### MCP 加路由

网关可以同时路由 LLM 调用**和** MCP 采样请求。当采样请求的 modelPreferences 偏好特定模型时，网关将其翻译到正确的后端。这就是 Phase 13 · 17（MCP 网关）和本课的路由网关有时合并为一个服务的地方。

### 路由策略

- **静态优先级。** 列表中的第一个；出错时回退。
- **负载均衡。** 轮询或加权。
- **成本感知。** 选择满足延迟/质量要求的最便宜模型。
- **延迟感知。** 选择最近 N 分钟内最快的模型。
- **任务感知。** 提示分类器将编码路由到一个模型，摘要路由到另一个。

## 使用方法

`code/main.py` 用约 150 行实现了一个路由网关：接受 OpenAI 形式的请求，翻译到每提供商的桩，运行优先级故障转移链，追踪每请求成本，并在输入上应用 PII 脱敏传递。用三个场景运行：正常请求、主提供商中断触发故障转移、PII 泄漏被脱敏捕获。

关注要点：

- `ROUTES` 字典：别名 -> 优先级排序的具体提供商列表。
- 故障转移循环在 5xx 时重试。
- 成本追踪器将 token 使用量乘以每模型费率。
- PII 脱敏器在转发前清理 SSN 形状的模式。

## 交付产出

本课产出 `outputs/skill-routing-config-designer.md`。给定工作负载配置（延迟、成本、合规），该技能选择 LiteLLM / OpenRouter / Portkey 并生成路由配置。

## 练习

1. 运行 `code/main.py`。触发中断场景；确认故障转移落到第二个提供商且成本正确归属。

2. 添加语义缓存：提示的 SHA256 是查找键；缓存命中立即返回。测量重复调用的成本节省。

3. 添加一个提示分类器，将"code ..."提示路由到偏好智能的别名，将"summarize ..."提示路由到偏好速度的别名。

4. 设计每团队预算：每个团队有月消费上限；达到上限后网关拒绝请求。选择强制粒度（每请求或窗口式）。

5. 并行阅读 LiteLLM、OpenRouter 和 Portkey 文档。说出每个提供的、另外两个没有的那个功能。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Routing Gateway（路由网关） | "LLM 代理" | 多个提供商前的统一 API 层 |
| OpenAI 兼容 | "说 OpenAI Schema" | 接受 `/v1/chat/completions` 形式，翻译到任何后端 |
| Model Alias（模型别名） | "our_smart_model" | 代码中的名称，网关映射到具体模型 |
| Fallback Chain（故障转移链） | "重试列表" | 故障时尝试的提供商有序列表 |
| Semantic Caching（语义缓存） | "提示嵌入缓存" | 键是提示的嵌入；近似重复共享缓存命中 |
| Guardrails（护栏） | "输入/输出过滤器" | 脱敏 PII，拒绝策略违规 |
| Per-key Rate Limit（每密钥速率限制） | "团队预算" | 限定到 API 密钥的配额 |
| Cost Tracking（成本追踪） | "每请求消费" | 聚合 token 使用量 x 每模型价格 |
| LiteLLM | "开源代理" | 可自托管的开源路由网关 |
| OpenRouter | "托管 SaaS" | 基于积分计费的托管网关 |
| Portkey | "生产选项" | 内置护栏的开源 + 托管 |

## 延伸阅读

- [LiteLLM — docs](https://docs.litellm.ai/) — 自托管路由网关
- [OpenRouter — quickstart](https://openrouter.ai/docs/quickstart) — 托管路由 SaaS
- [Portkey — docs](https://portkey.ai/docs) — 带护栏的生产路由
- [TrueFoundry — LiteLLM vs OpenRouter](https://www.truefoundry.com/blog/litellm-vs-openrouter) — 决策指南
- [Relayplane — LLM gateway comparison 2026](https://relayplane.com/blog/llm-gateway-comparison-2026) — 厂商调研