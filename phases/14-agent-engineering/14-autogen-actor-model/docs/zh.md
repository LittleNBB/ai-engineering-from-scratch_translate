# AutoGen v0.4：Actor 模型与 Agent 框架

> AutoGen v0.4（Microsoft Research，2025 年 1 月）围绕 Actor 模型重新设计了 Agent 编排。异步消息交换、事件驱动 Agent、故障隔离、天然并发。该框架目前处于维护模式，Microsoft Agent Framework（2025 年 10 月公开预览）成为其继任者。

**类型：** Learn + Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 01（Agent Loop）、Phase 14 · 12（Workflow Patterns）
**时间：** ~75 分钟

## 学习目标

- 描述 Actor 模型：Agent 即 Actor，消息是唯一的 IPC，每个 Actor 故障隔离。
- 说出 AutoGen v0.4 的三层 API —— Core、AgentChat、Extensions —— 及其各自用途。
- 解释为什么将消息传递与处理解耦能带来故障隔离和天然并发。
- 用 Python 实现一个标准库 Actor 运行时，并将一个双 Agent 代码审查流程移植到上面。

## 问题

大多数 Agent 框架是同步的：一个 Agent 产生，一个 Agent 消费，在一个调用栈中。故障会崩溃整个栈。并发是后加的。分发需要重写。

AutoGen v0.4 的答案：Actor 模型。每个 Actor 有一个私有收件箱。消息是唯一的交互方式。运行时将传递与处理解耦。故障隔离到一个 Actor。并发是原生的。分发只是不同的传输。

## 核心概念

### Actor

一个 Actor 有：

- 私有状态（从不被外部直接触碰）。
- 收件箱（消息队列）。
- 处理器：`receive(message) -> effects`，其中效果可以是"回复"、"发送给其他 Actor"、"生成新 Actor"、"更新状态"、"停止自身"。

两个 Actor 不能共享内存。它们只能发送消息。

### AutoGen v0.4 的三层 API

1. **Core。** 底层 Actor 框架。`AgentRuntime`、`Agent`、`Message`、`Topic`。异步消息交换，事件驱动。
2. **AgentChat。** 任务驱动的高层 API（v0.2 ConversableAgent 的替代品）。`AssistantAgent`、`UserProxyAgent`、`RoundRobinGroupChat`、`SelectorGroupChat`。
3. **Extensions。** 集成 —— OpenAI、Anthropic、Azure、工具、记忆。

### 为什么解耦很重要

在 v0.2 模型中，调用 `agent_a.chat(agent_b)` 会同步阻塞 agent_a 直到 agent_b 返回。在 v0.4 中，`send(agent_b, msg)` 将消息放入 agent_b 的收件箱然后返回。运行时稍后传递。三个后果：

- **故障隔离。** Agent B 崩溃不会崩溃 Agent A —— 运行时在 B 的处理器中捕获故障并决定做什么（记录、重试、死信）。
- **天然并发。** 许多消息同时在飞行中；Actor 并发处理它们的收件箱。
- **分发就绪。** 收件箱 + 传输是相同的抽象，无论 Actor 是在进程内还是在另一台主机上。

### 拓扑

- **RoundRobinGroupChat。** Agent 按固定轮流顺序发言。
- **SelectorGroupChat。** 选择器 Agent 根据对话上下文选择下一个发言者。
- **Magentic-One。** 用于 Web 浏览、代码执行、文件处理的参考多 Agent 团队。基于 AgentChat 构建。

### 可观测性

内置 OpenTelemetry 支持。每个消息发出一个 span；工具调用携带 `gen_ai.*` 属性，符合 2026 年 OTel GenAI 语义约定（第 23 课）。

### 状态：维护模式

2026 年初：AutoGen v0.7.x 对研究和原型开发稳定。Microsoft 已将积极开发转向 Microsoft Agent Framework（2025 年 10 月 1 日公开预览；1.0 GA 目标 2026 年 Q1 末）。AutoGen 模式可以干净地向前移植 —— Actor 模型是持久的思想。

## 构建它

`code/main.py` 实现了一个标准库 Actor 运行时：

- `Message` — 带 `sender`、`recipient`、`topic`、`body` 的类型化负载。
- `Actor` — 抽象类，带 `receive(message, runtime)`。
- `Runtime` — 带共享队列、传递、故障隔离的事件循环。
- 双 Actor 演示：`ReviewerAgent` 审查代码，`ChecklistAgent` 运行检查清单；它们交换消息直到达成共识。

运行它：

```
python3 code/main.py
```

轨迹展示了消息传递、一个 Actor 中的模拟故障不会崩溃另一个，以及收敛到共享结论。

## 使用它

- **AutoGen v0.4/v0.7**（维护模式）—— 对研究、原型开发、多 Agent 模式稳定。
- **Microsoft Agent Framework**（公开预览）—— 前进路径；刷新 API 中相同的 Actor 模型思想。
- **LangGraph 蜂群拓扑**（第 13 课）—— 通过共享工具交接的类似模式。
- **自定义 Actor 运行时** — 当你需要特定传输（NATS、RabbitMQ、gRPC）时。

## 发布它

`outputs/skill-actor-runtime.md` 生成一个最小 Actor 运行时加团队模板（RoundRobin 或 Selector），用于给定的多 Agent 任务。

## 练习

1. 添加死信队列：当处理器抛出异常时，将失败消息停放供人工检查。在你的玩具中 DLQ 被命中的频率如何？
2. 实现 `SelectorGroupChat`：一个选择器 Actor 根据对话状态选择谁处理下一条消息。
3. 添加分布式传输：将进程内队列换为 JSON-over-HTTP 服务器，使 Actor 可以在独立进程中运行。
4. 接线每条消息一个 OTel span（或无操作替代品）。按第 23 课发出 `gen_ai.agent.name`、`gen_ai.operation.name`。
5. 阅读 AutoGen v0.4 的架构帖子。将你的玩具移植到真实的 `autogen_core` API。你跳过了什么在生产中重要的东西？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Actor | "Agent" | 私有状态 + 收件箱 + 处理器；无共享内存 |
| Message | "事件" | 类型化负载；Actor 交互的唯一方式 |
| Inbox | "邮箱" | 每个 Actor 的待处理消息队列 |
| Runtime | "Agent 宿主" | 路由消息和隔离故障的事件循环 |
| Topic | "通道" | Actor 之间的命名发布-订阅路由 |
| Fault isolation | "让它崩溃" | 一个 Actor 失败不会崩溃其他 Actor |
| RoundRobinGroupChat | "固定轮流团队" | Agent 按顺序轮流发言 |
| SelectorGroupChat | "上下文路由团队" | 选择器选择下一个发言者 |
| Magentic-One | "参考团队" | 用于 Web + 代码 + 文件的多 Agent 小队 |

## 延伸阅读

- [AutoGen v0.4, Microsoft Research](https://www.microsoft.com/en-us/research/articles/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness/) — 重设计帖子
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) — 图形替代方案
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — AutoGen 默认发出的 span