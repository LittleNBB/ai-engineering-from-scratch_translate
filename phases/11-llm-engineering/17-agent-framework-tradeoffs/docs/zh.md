# 代理框架权衡 — LangGraph vs CrewAI vs AutoGen vs Agno

> 每个框架都兜售相同的演示（研究代理构建报告）并隐藏相同的 bug（状态模式与编排层冲突）。选择抽象匹配你问题形状的框架；其他一切都是你要写两遍的胶水代码。

**类型:** Learn
**语言:** Python
**前置课程:** Phase 11 · 09 (函数调用), Phase 11 · 16 (LangGraph)
**时间:** ~45 分钟

## 问题

你有一个需要多次 LLM 调用的任务。可能是一个研究工作流（计划、搜索、总结、引用）。可能是一个代码审查流水线（解析 diff、评论、打补丁、验证）。可能是一个多轮助手，可以预订航班、写邮件和提交费用报告。你选择了一个框架。

三天后，你发现框架的抽象在泄露。CrewAI 给你角色，但当"研究员"需要将结构化计划交给"作者"时会跟你对抗。AutoGen 给你代理之间的聊天，但没有一等状态，所以你的检查点是对话日志的 pickle。LangGraph 给你一个状态图，但在你知道代理会做什么之前就强迫你命名每个转换。Agno 给你一个单代理抽象，当你尝试扇出到三个并发工作者时会尖叫。

修复方法不是"选择最好的框架"。而是将框架的核心抽象与你问题的形状匹配。本课程画出那张地图。

## 概念

![Agent framework matrix: core abstraction vs problem shape](../assets/framework-matrix.svg)

四个框架主导 2026 年的格局。它们的核心抽象并不相同。

| 框架 | 核心抽象 | 最适合 | 最不适合 |
|------|---------|--------|---------|
| **LangGraph** | `StateGraph` — 类型化状态、节点、条件边、检查器。 | 具有显式状态和人机交互中断的工作流；需要时间旅行调试的生产代理。 | 拓扑未知的松散、角色驱动的头脑风暴。 |
| **CrewAI** | `Crew` — 角色（目标、背景故事）、任务、流程（顺序或层次）。 | 具有短的线性/层次计划的角色扮演或人格驱动工作流。 | 超出团队轮次历史的任何有状态内容；复杂分支。 |
| **AutoGen** | `ConversableAgent` 对 — 两个或更多代理轮流对话直到退出条件。 | 多代理*对话*（师生、提议者-批评者、演员-审阅者），思考从聊天中涌现。 | 具有已知 DAG 的确定性工作流；任何需要跨重启持久状态的内容。 |
| **Agno** | `Agent` — 单个 LLM + 工具 + 记忆，可组合成团队。 | 快速构建的单代理和轻量级团队；强大的多模态和内置存储驱动。 | 具有自定义归约器的深度、显式分支图。 |

### "抽象"实际意味着什么

框架的核心抽象是你在白板上推销架构时画的东西。

- **LangGraph** → 你画一个图。节点是步骤，边是转换，每个点的状态对象是类型化的。心理模型是状态机。
- **CrewAI** → 你画一个组织图。每个角色有职位描述，经理路由任务。心理模型是一个小型专家团队。
- **AutoGen** → 你画一个 Slack 私信。两个代理互相发消息；如果你需要主持人，第三个加入。心理模型是聊天。
- **Agno** → 你画一个带工具的方框。并排放置方框组成团队。心理模型是"自带电池的代理"。

### 状态问题

状态是大多数框架选择在生产中崩溃的地方。

- **LangGraph。** 类型化状态（`TypedDict` 或 Pydantic 模型），每字段归约器，一等检查器（SQLite/Postgres/Redis）。恢复、中断和时间旅行是免费的。*（参见 Phase 11 · 16。）*
- **CrewAI。** 状态通过 `context` 字段在任务之间以字符串流动，或通过 `output_pydantic` 以结构化方式流动。开箱即用没有持久化的每团队存储；如果团队必须在重启后存活，你需要自己附加。
- **AutoGen。** 状态是聊天历史和任何用户定义的 `context`。对话记录持久化；任意工作流状态不会，除非你编写适配器。
- **Agno。** 内置存储驱动（SQLite、Postgres、Mongo、Redis、DynamoDB）通过 `storage=` 附加到 `Agent`——对话会话和用户记忆自动持久化。不是完整的图检查器；是会话存储。

### 分支问题

每个非平凡的代理都会分支。谁决定分支很重要。

- **LangGraph** — 你决定，通过条件边。路由是一个带命名分支的 Python 函数。分支在编译的图中是一等的；检查器记录了走了哪个分支。
- **CrewAI** — 经理在层次模式下决定；在顺序模式下你在构建时决定。路由隐含在任务列表中；经理提示之外没有一等的"if"。
- **AutoGen** — 代理通过聊天决定。分支从谁下一个说话中涌现。`GroupChatManager` 选择下一个说话者；你可以手写 `speaker_selection_method`，但默认是 LLM 驱动的。
- **Agno** — 代理通过调用哪个工具来决定。团队有协调器/路由器/协作者模式；超出这一点的分支是开发者的责任。

### 可观测性问题

- **LangGraph** — 通过 LangSmith 或任何 OTel 导出器的 OpenTelemetry。每次节点转换都是一个追踪跨度；检查器同时作为可重放的追踪。LangSmith 是第一方选项；Langfuse/Phoenix 也有适配器。
- **CrewAI** — 自 2025 年底以来的一等 OpenTelemetry；与 Langfuse、Phoenix、Opik、AgentOps 集成。
- **AutoGen** — 通过 `autogen-core` 的 OpenTelemetry 集成；AgentOps 和 Opik 有连接器。追踪粒度是每代理消息，不是每节点。
- **Agno** — 内置 `monitoring=True` 标志加 OpenTelemetry 导出器；与 Langfuse 紧密集成用于会话追踪。

### 成本和延迟

所有四个框架都增加每次调用的开销（框架逻辑、验证、序列化）。开销从低到高的大致顺序：Agno ≈ LangGraph < CrewAI ≈ AutoGen。差异主要由框架做多少额外的 LLM 路由决定。CrewAI 的层次经理花 token 决定谁下一步；AutoGen 的 `GroupChatManager` 同样如此。LangGraph 只在你写 `llm.invoke` 的地方花 token。Agno 的单代理路径很薄。

当每次运行的成本很重要时，优先选择显式路由（LangGraph 边、AutoGen `speaker_selection_method`）而非 LLM 选择的路由。

### 互操作性

- **LangGraph** ↔ **LangChain** 工具、检索器、LLM。一等 MCP 适配器（工具作为 MCP 服务器导入）。
- **CrewAI** ↔ 工具继承自 `BaseTool`；LangChain 工具、LlamaIndex 工具和 MCP 工具都可以适配。通过 `allow_delegation=True` 的团队间委派。
- **AutoGen** → `FunctionTool` 包装任何 Python 可调用对象；MCP 适配器可用。与 AG2 生态系统紧密耦合用于代理到代理模式。
- **Agno** → `@tool` 装饰器或 BaseTool 子类；MCP 适配器；工具可在代理和团队间共享。

## 技能

> 你能用一句话解释为什么给定的框架适合给定的代理问题。

构建前检查清单：

1. **画出形状。** 这是一个图（类型化状态、命名转换）？一个角色扮演（专家交接工作）？一个聊天（代理对话直到完成）？一个带工具的单代理？
2. **决定谁分支。** 开发者决定分支 → LangGraph。管理代理决定 → CrewAI 层次。聊天涌现 → AutoGen。工具调用决定 → Agno。
3. **检查状态预算。** 你需要从检查点恢复？时间旅行？运行中的人工中断？如果是，LangGraph 是默认选择；Agno 会话覆盖对话范围的状态。
4. **检查成本预算。** LLM 选择的路由每轮额外花费 token。如果代理每天运行数千次，优先选择显式路由。
5. **预算框架开销。** 每个框架都是另一个依赖。如果任务是两次 LLM 调用和一个工具，写 30 行纯 Python；没有框架比没有框架更便宜。

在你能画出图、组织图、聊天或代理方框之前，拒绝使用框架。选择一个迫使你为其状态模型而战来实现你实际需要的东西的框架。

## 决策矩阵

| 问题形状 | 首选框架 | 原因 |
|---------|---------|------|
| 带类型化状态、人工审批、长时间运行的工作流 DAG | LangGraph | 一等状态、检查器、中断、时间旅行。 |
| 具有不同角色的研究/写作流水线 | CrewAI（顺序）或 LangGraph 子图 | 每任务一个角色在 CrewAI 中表达成本低；当分支变复杂时用 LangGraph 扩展。 |
| 提议者-批评者或师生对话 | AutoGen | 两人聊天是其原生形状。 |
| 带工具、会话、记忆的单代理 | Agno | 最薄的设置，内置存储和记忆。 |
| 数千个并行扇出带归约器 | LangGraph + `Send` | 唯一具有一等并行派发 API 的。 |
| 快速原型，无框架承诺 | 纯 Python + 提供商 SDK | 没有框架就是最快的框架。 |

## 练习

1. **简单。** 取同一个任务——"研究 Anthropic 总部，写 200 字简介，引用来源"——分别在 LangGraph（四个节点：计划、搜索、写作、引用）和 CrewAI（三个角色：研究员、作者、编辑）中实现。报告每次运行的 token 成本和代码行数。
2. **中等。** 在 AutoGen（研究员 ↔ 作者聊天，编辑通过 `GroupChat` 加入）和 Agno（一个带 `search_tools` 和 `write_tools` 的单代理，加会话存储）中构建同一任务。按 (a) 每次运行成本、(b) 崩溃后恢复能力、(c) 在写入步骤前注入人工审批的能力对四个实现排名。
3. **困难。** 构建一个决策树脚本 `pick_framework.py`，接受简短的问题描述（JSON：`{has_typed_state, has_roles, has_dialogue, has_parallel_fanout, needs_resume}`）并返回带一句话理由的建议。在你自己设计的六个案例上验证。

## 关键术语

| 术语 | 人们怎么说 | 它的实际含义 |
|------|-----------|-------------|
| Orchestration | "代理如何协调" | 决定哪个节点/角色/代理下一步运行的层。 |
| Durable state | "重启后恢复" | 在进程死亡后存活的状态，附加到检查点或会话存储。 |
| LLM-selected routing | "让模型决定" | 规划器 LLM 每轮选择下一步；灵活但每次决策都花 token。 |
| Explicit routing | "开发者决定" | Python 函数或静态边选择下一步；便宜且可审计。 |
| Crew | "CrewAI 团队" | 角色 + 任务 + 流程（顺序或层次）绑定到单个可运行对象。 |
| GroupChat | "AutoGen 的多代理聊天" | N 个代理之间的托管对话，带说话者选择器。 |
| Team (Agno) | "多代理 Agno" | 一组代理上的路由/协调/协作模式。 |
| StateGraph | "LangGraph 的图" | 类型化状态、节点、条件边、检查器抽象。 |

## 延伸阅读

- [LangGraph 文档](https://langchain-ai.github.io/langgraph/) — StateGraph、检查器、中断、时间旅行。
- [CrewAI 文档](https://docs.crewai.com/) — Crews、Flows、Agents、Tasks、Processes。
- [AutoGen 文档](https://microsoft.github.io/autogen/) — ConversableAgent、GroupChat、teams、tools。
- [Agno 文档](https://docs.agno.com/) — Agent、Team、Workflow、storage、memory。
- [Anthropic — 构建有效代理 (2024 年 12 月)](https://www.anthropic.com/research/building-effective-agents) — 模式库（提示链、路由、并行化、编排器-工作者、评估器-优化器）框架无关。
- [Yao et al., "ReAct: Synergizing Reasoning and Acting" (ICLR 2023)](https://arxiv.org/abs/2210.03629) — 每个框架都在包装的循环。
- [Wu et al., "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation" (2023)](https://arxiv.org/abs/2308.08155) — AutoGen 的设计论文。
- [Park et al., "Generative Agents: Interactive Simulacra of Human Behavior" (UIST 2023)](https://arxiv.org/abs/2304.03442) — CrewAI 风格的人格堆栈所建立的角色扮演基础。
- Phase 11 · 16 (LangGraph) — 本课程对标基准的框架。
- Phase 11 · 19 (Reflexion) — 一个干净地映射到 LangGraph 但笨拙地映射到 CrewAI 的模式。
- Phase 11 · 22 (生产可观测性) — 如何检测你选择的任何框架。