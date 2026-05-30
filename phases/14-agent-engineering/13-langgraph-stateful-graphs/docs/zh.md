# LangGraph：有状态图与持久执行

> LangGraph 是 2026 年底层有状态编排的参考。Agent 是状态机；节点是函数；边是转换；状态是不可变的，每步后检查点。从任何故障处精确恢复到中断的位置。

**类型：** Learn + Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 01（Agent Loop）、Phase 14 · 12（Workflow Patterns）
**时间：** ~75 分钟

## 学习目标

- 描述 LangGraph 的核心模型：带不可变状态、函数节点、条件边和每步后检查点的状态机。
- 说出文档强调的四种能力：持久执行、流式传输、人机协作、全面记忆。
- 解释 LangGraph 支持的三种编排拓扑：监督者（supervisor）、点对点（swarm/蜂群）、层级式（嵌套子图）。
- 用标准库实现一个带不可变状态、条件边和检查点/恢复周期的状态图。

## 问题

Agent 和工作流共享一个问题：当一个 40 步的运行在第 38 步失败时，你想从第 38 步恢复，而不是重新开始。二等状态模型让运维人员围绕一个假设全新运行的库来拼凑重试。

LangGraph 的设计答案：状态是一等类型化对象，变更是显式的，检查点在每个节点后持久化。恢复是 `load_state(session_id)` 调用。

## 核心概念

### 图

一个图由以下定义：

- **状态类型。** 一个类型化 dict（或 Pydantic 模型），每个节点读取和变更。
- **节点。** 纯函数 `(state) -> state_update`。返回后更新合并到状态中。
- **边。** 节点之间的条件或直接转换。
- **入口和出口。** `START` 和 `END` 哨兵节点标记边界。

示例：一个带 `classify`、`refund`、`bug`、`sales`、`done` 节点的 Agent —— 作为图的路由工作流。

### 持久执行

每个节点返回后，运行时序列化状态并将其写入检查点器（SQLite、Postgres、Redis、自定义）。在第 N 步失败时，运行时可以 `resume(session_id)` 并从第 N+1 步以精确状态继续。

LangGraph 文档明确强调了重要的生产用户：Klarna、Uber、J.P. Morgan。声明不是图的形状；而是图的形状加上检查点使恢复变得廉价。

### 流式传输

每个节点可以产出部分输出。图向调用者流式传输每节点增量事件，以便 UI 在图运行时更新。

### 人机协作

在节点之间检查和修改状态。实现方式：在关键节点前暂停，将状态呈现给人类，接受修改，恢复。检查点器使这变得容易，因为状态已经被序列化。

### 记忆

短期（运行内 —— 状态中的对话历史）和长期（跨运行 —— 通过检查点器加单独的长期存储持久化）。LangGraph 通过工具与外部记忆系统（Mem0、自定义）集成。

### 三种拓扑

1. **监督者（Supervisor）。** 中央路由器 LLM 分发到专家子 Agent。`langgraph-supervisor` 中的 `create_supervisor()`（尽管 LangChain 团队在 2026 年建议通过工具调用直接实现以获得更好的上下文控制）。
2. **蜂群/点对点（Swarm / peer-to-peer）。** Agent 通过共享工具接口直接交接。无中央路由器。
3. **层级式（Hierarchical）。** 监督者管理子监督者，实现为嵌套子图。

### 这个模式出错的地方

- **检查点太小。** 仅检查点对话轮次会使工具状态和记忆写入无法恢复。完整状态必须可序列化。
- **非确定性节点。** 恢复假设节点输入产生相同的状态更新。随机种子、挂钟时间、外部 API 必须被捕获。
- **条件边过度使用。** 每条边都是条件的图是一个无法推理的状态机。优先使用偶尔有分支的线性链。

## 构建它

`code/main.py` 实现了一个标准库有状态图：

- `State` — 带 `messages`、`step`、`route`、`output`、`human_approval` 的类型化 dict。
- `Node` — 接受状态并返回更新 dict 的可调用对象。
- `StateGraph` — 节点 + 边 + 条件边 + 运行 + 恢复。
- `SQLiteCheckpointer`（内存假实现）—— 每个节点后序列化状态；`load(session_id)` 恢复。
- 演示图：classify -> branch(refund / bug / sales) -> human gate -> send。

运行它：

```
python3 code/main.py
```

轨迹展示了第一次运行在人工门控处失败、持久化、然后恢复产生最终输出。

## 使用它

- **LangGraph** — 参考实现，生产就绪。使用 `create_react_agent`、`create_supervisor`，或构建自己的图。
- **AutoGen v0.4**（第 14 课）—— 高并发场景的 Actor 模型替代方案。
- **Claude Agent SDK**（第 17 课）—— 带内置会话存储的托管框架。
- **自定义** — 当你需要精确控制状态形状或检查点器后端时。

## 发布它

`outputs/skill-state-graph.md` 在任何目标运行时生成 LangGraph 形态的状态图，带检查点和恢复。

## 练习

1. 当分类置信度低于阈值时，从 `classify` 添加到 `end` 的条件边。在人工手动设置 `route` 后恢复运行。
2. 将 SQLite 类假实现换成真实的 SQLite 检查点器。衡量每步序列化开销。
3. 实现并行边：两个节点并发运行，通过自定义 reducer 合并。不可变状态在这里带来什么好处？
4. 阅读 `langgraph-supervisor` 参考文档。将玩具代码移植到 `create_supervisor`。比较轨迹形状。
5. 添加流式传输：每个节点在运行时产出部分状态。在到达时打印增量。

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| State graph | "Agent 即状态机" | 类型化状态 + 节点 + 边 + reducer |
| Checkpointer | "持久化后端" | 每个节点后序列化状态；使恢复成为可能 |
| Reducer | "状态合并器" | 将当前状态与节点更新合并的函数 |
| Conditional edge | "分支" | 由状态函数选择的边 |
| Subgraph | "嵌套图" | 在另一个图中用作节点的图 |
| Durable execution | "从故障恢复" | 以精确状态在最后成功的节点重启 |
| Supervisor | "路由器 LLM" | 专家子 Agent 的中央分发器 |
| Swarm | "P2P Agent" | Agent 通过共享工具交接；无中央路由器 |

## 延伸阅读

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) — 参考文档
- [langgraph-supervisor reference](https://reference.langchain.com/python/langgraph/supervisor/) — 监督者模式 API
- [AutoGen v0.4, Microsoft Research](https://www.microsoft.com/en-us/research/articles/autogen-v0-4-reimagining-the-foundation-of-agentic-ai-for-scale-extensibility-and-robustness/) — Actor 模型替代方案
- [Claude Agent SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview) — 会话存储和子 Agent