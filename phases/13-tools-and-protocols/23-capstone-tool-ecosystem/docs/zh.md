# 毕业设计 — 构建完整的工具生态系统

> Phase 13 教了每一个组件。这个毕业设计将它们串联成一个生产形态的系统：一个带 tools + resources + prompts + tasks + UI 的 MCP 服务器、边缘的 OAuth 2.1、RBAC 网关、多服务器客户端、A2A 子 Agent 调用、到收集器的 OTel 追踪、CI 中的工具投毒检测、以及 AGENTS.md + SKILL.md 组合。完成后你可以为每个架构选择辩护。

**类型：** Build
**语言：** Python（stdlib，端到端生态系统脚手架）
**前置课程：** Phase 13 · 01 到 21
**时间：** ~120 分钟

## 学习目标

- 组合一个暴露 tools、resources、prompts 和带 `ui://` app 的 task 的 MCP 服务器。
- 用强制 RBAC 和固定 hash 的 OAuth 2.1 网关前置服务器。
- 编写一个用 OTel GenAI 属性端到端追踪的多服务器客户端。
- 将部分工作负载委托给 A2A 子 Agent；验证不透明性被保持。
- 用 AGENTS.md + SKILL.md 打包整个技术栈，使其他 Agent 可以驱动它。

## 问题

发布"研究与报告"系统：

- 用户问："总结 2026 年三篇被引用最多的关于 Agent 协议的 arXiv 论文。"
- 系统：通过 MCP 搜索 arXiv；通过 A2A 将论文摘要委托给专门的写手 Agent；聚合结果；将交互式报告渲染为 MCP Apps `ui://` 资源；将每一步记录到 OTel。

Phase 13 的所有原语都出现了。这不是玩具 — 2026 年由 Anthropic（Claude Research 产品）、OpenAI（带 Apps SDK 的 GPTs）和第三方发布生产研究助手系统就具有这种确切形态。

## 核心概念

### 架构

```
[user] -> [client] -> [gateway (OAuth 2.1 + RBAC)] -> [research MCP server]
                                                      |
                                                      +- MCP tool: arxiv_search (pure)
                                                      +- MCP resource: notes://recent
                                                      +- MCP prompt: /research_topic
                                                      +- MCP task: generate_report (long)
                                                      +- MCP Apps UI: ui://report/current
                                                      +- A2A call: writer-agent (tasks/send)
                                                      |
                                                      +- OTel GenAI spans
```

### Trace 层次结构

```
agent.invoke_agent
 ├── llm.chat (kick off)
 ├── mcp.call -> tools/call arxiv_search
 ├── mcp.call -> resources/read notes://recent
 ├── mcp.call -> prompts/get research_topic
 ├── a2a.tasks/send -> writer-agent
 │    └── task transitions (opaque internals)
 ├── mcp.call -> tools/call generate_report (task-augmented)
 │    └── tasks/status polling
 │    └── tasks/result (completed, returns ui:// resource)
 └── llm.chat (final synthesis)
```

一个 trace id。每个 span 都有正确的 `gen_ai.*` 属性。

### 安全态势

- OAuth 2.1 + PKCE，带资源指示器将受众固定到网关。
- 网关持有上游凭证；用户永远看不到。
- RBAC：`alice` 有 `research:read`、`research:write`，可以调用所有工具。`bob` 有 `research:read`，不能调用 `generate_report`。
- 固定描述清单：丢弃了任何工具 hash 变更的服务器。
- 二元法则审计：没有工具同时组合不可信输入、敏感数据和有副作用的动作。

### 渲染

最终的 `generate_report` 任务返回内容块加一个 `ui://report/current` 资源。客户端的宿主（Claude Desktop 等）在沙箱 iframe 中渲染交互式仪表板。仪表板包含排序的论文列表、引用计数，以及一个按钮，用户点击任何论文时调用 `host.callTool('summarize_paper', {arxiv_id})`。

### 打包

整个系统以如下形式发布：

```
research-system/
  AGENTS.md                     # 项目约定
  skills/
    run-research/
      SKILL.md                  # 顶层工作流
  servers/
    research-mcp/               # MCP 服务器
      pyproject.toml
      src/
  agents/
    writer/                     # A2A Agent
  gateway/
    config.yaml                 # RBAC + 固定清单
```

用户用 `docker compose up` 部署。Claude Code、Cursor、Codex 和 opencode 用户可以通过调用 `run-research` 技能来驱动系统。

### Phase 13 每课的贡献

| 课程 | 毕业设计使用的内容 |
|------|-------------------|
| 01-05 | 工具接口、提供商可移植性、并行调用、Schema、检查 |
| 06-10 | MCP 原语、服务器、客户端、传输层、资源 + 提示模板 |
| 11-14 | 采样、根目录 + 引出、异步任务、`ui://` 应用 |
| 15-17 | 工具投毒、OAuth 2.1、网关 + 注册表 |
| 18 | A2A 子 Agent 委托 |
| 19 | OTel GenAI 追踪 |
| 20 | LLM 层的路由网关 |
| 21 | SKILL.md + AGENTS.md 打包 |

## 使用方法

`code/main.py` 将前面课程的模式串联成一个可运行的演示。全部标准库，全部在进程中，你可以端到端阅读。它运行研究与报告场景的完整流程：与网关握手、模拟 OAuth 2.1、合并 tools/list、将 generate_report 作为任务、A2A 调用写手、返回 ui:// 资源、发出 OTel span。

关注要点：

- 一个 trace id 贯穿每一跳。
- 网关策略阻止第二个用户写入。
- Task 生命周期从 working → completed 并同时返回文本和 ui:// 内容。
- A2A 调用的内部状态对编排者不透明。
- AGENTS.md 和 SKILL.md 是另一个 Agent 复现工作流所需的唯一文件。

## 交付产出

本课产出 `outputs/skill-ecosystem-blueprint.md`。给定产品需求（研究、摘要、自动化），该技能生成完整架构：哪些 MCP 原语、哪些网关控制、哪些 A2A 调用、哪些遥测、哪些打包。

## 练习

1. 运行 `code/main.py`。注意单个 trace id 和 span 如何嵌套。统计演示涉及了 Phase 13 的多少个原语。

2. 扩展演示：添加第二个后端 MCP 服务器（如 `bibliography`），确认网关将其工具合并到同一命名空间。

3. 用运行在子进程上的真实 A2A 写手 Agent 替换假的。使用 Lesson 19 的脚手架。

4. 在路由网关中添加 PII 脱敏步骤，位于编排器和 LLM 之间。确认用户查询中的邮箱被清理。

5. 为维护此系统的队友编写一个 AGENTS.md。应该在五分钟内读完，给他们在 Cursor 或 Codex 中驱动毕业设计所需的一切。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Capstone（毕业设计） | "Phase 13 集成演示" | 使用每个原语的端到端系统 |
| Research and Report（研究与报告） | "那个场景" | 搜索、摘要、渲染模式 |
| Ecosystem（生态系统） | "所有组件放在一起" | 服务器 + 客户端 + 网关 + 子 Agent + 遥测 + 打包 |
| Trace 层次结构 | "单个 trace id" | 每跳的 span 共享 trace；父子关系通过 span id |
| 网关颁发的 token | "传递性认证" | 客户端只看到网关的 token；网关持有上游凭证 |
| 合并命名空间 | "所有工具在一个扁平列表中" | 网关处的多服务器合并，冲突时加前缀 |
| 不透明性边界 | "A2A 调用隐藏内部" | 子 Agent 的推理对编排者不可见 |
| 三层技术栈 | "AGENTS.md + SKILL.md + MCP" | 项目上下文 + 工作流 + 工具 |
| 纵深防御 | "多层安全" | 固定 hash、OAuth、RBAC、二元法则、审计日志 |
| 规范合规矩阵 | "规范要求我们交付什么" | 将交付物映射到 2025-11-25 要求的清单 |

## 延伸阅读

- [MCP — Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) — 合并参考
- [MCP blog — 2026 roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) — 协议的发展方向
- [a2a-protocol.org](https://a2a-protocol.org/latest/) — A2A v1.0 参考
- [OpenTelemetry — GenAI semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — 规范性追踪约定
- [Anthropic — Claude Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview) — 生产 Agent 运行时模式