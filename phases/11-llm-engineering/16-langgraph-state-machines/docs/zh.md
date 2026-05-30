# LangGraph — 代理的状态机

> 手写的 ReAct 循环是一个 `while True`。用 LangGraph 写的 ReAct 循环是一个你可以检查点、中断、分支和时间旅行的图。代理没有变。围绕它的工具变了。

**类型:** Build
**语言:** Python
**前置课程:** Phase 11 · 09 (函数调用), Phase 11 · 14 (模型上下文协议)
**时间:** ~75 分钟

## 问题

你发布了一个函数调用代理。它工作了三轮，然后出了问题：模型尝试了一个返回 500 的工具，用户在任务中途改变了主意，或者代理决定退款订单而没有人工签字。`while True:` 循环没有钩子。你无法暂停它，无法回退它，也无法分支到"如果模型选了另一个工具会怎样"。一旦你将它发布到演示之外，代理就成了一个要么成功要么失败的黑盒。

一旦你看到它，下一步就很明显了。代理已经是一个状态机——系统提示加消息历史加待处理的工具调用加下一个动作。让状态机显式化：节点用于"模型思考"、"工具运行"、"人工审批"，边用于它们之间的条件转换。一旦图是显式的，工具就免费获得四样东西：检查点（在步骤之间保存状态）、中断（暂停等待人工）、流式传输（传输 token 和中间事件）和时间旅行（回退到之前的状态并尝试不同的分支）。

LangGraph 是实现这个抽象的库。它不是 LangChain 意义上的代理框架（"这是一个 AgentExecutor，祝你好运"）。它是一个具有一等状态、一等持久化和一等中断的图运行时。代理循环是你画出来的东西，而不是你手写的东西。

## 概念

![LangGraph StateGraph: nodes, edges, and the checkpointer](../assets/langgraph-stategraph.svg)

一个 `StateGraph` 有三样东西。

1. **状态。** 一个类型化字典（TypedDict 或 Pydantic 模型）在图中流动。每个节点接收完整状态并返回部分更新，LangGraph 使用每个字段的*归约器*（reducer）进行合并——对于应该累积的列表使用 `operator.add`，默认是覆盖。
2. **节点。** Python 函数 `state -> partial_state`。每个是一个离散步骤："调用模型"、"运行工具"、"摘要"。
3. **边。** 节点之间的转换。静态边去一个地方。条件边取一个路由器函数 `state -> next_node_name`，以便图可以根据模型输出分支。

你编译图。Compile 绑定拓扑，附加一个检查器（可选但对生产至关重要），并返回一个可运行对象。你用初始状态和 `thread_id` 调用它。执行的每一步都持久化一个以 `(thread_id, checkpoint_id)` 为键的检查点。

### 四个超能力

**检查点。** 每次节点转换都将新状态写入存储（测试用内存，生产用 Postgres/Redis/SQLite）。通过用相同的 `thread_id` 再次调用图来恢复。图从暂停处继续。

**中断。** 用 `interrupt_before=["human_review"]` 标记节点，执行在该节点运行前停止。状态持久化。你的 API 用"等待审批"响应用户。稍后对同一 `thread_id` 的请求用 `Command(resume=...)` 恢复执行。

**流式传输。** `graph.stream(state, mode="updates")` 在发生时生成状态增量。`mode="messages"` 在模型节点内流式传输 LLM token。`mode="values"` 生成完整快照。你选择在 UI 中展示什么。

**时间旅行。** `graph.get_state_history(thread_id)` 返回完整的检查点日志。将任何之前的 `checkpoint_id` 传给 `graph.invoke`，你就从该点分叉。非常适合调试（"如果模型选了工具 B 会怎样？"）和回放生产追踪的回归测试。

### 归约器是关键

每个状态字段都有一个归约器。大多数默认值没问题——新值覆盖旧值。但消息列表需要 `operator.add`，这样新消息才会追加而非替换。并行边通过归约器合并它们的更新。如果两个节点都更新 `messages` 而你忘了 `Annotated[list, add_messages]`，第二个会静默胜出，你会丢失一半的轮次。归约器是库中唯一微妙的东西；把它搞对，其余的就能组合。

### 四个节点的 ReAct 图

一个生产 ReAct 代理是四个节点和两条边：

1. `agent` — 用当前消息历史调用 LLM。返回助手消息（可能包含 tool_calls）。
2. `tools` — 执行最后一条助手消息中的所有 tool_calls，将工具结果作为工具消息追加。
3. 从 `agent` 的条件边，如果最后一条消息有 tool_calls 则路由到 `tools`，否则到 `END`。
4. 从 `tools` 回到 `agent` 的静态边。

就这样。你在大约 40 行代码中获得完整的 ReAct 循环（思考 → 行动 → 观察 → 思考 → …），带检查点、中断和流式传输。

### StateGraph vs Send（扇出）

`Send(node_name, state)` 让节点派发并行子图。示例：代理决定同时查询三个检索器。每个 `Send` 生成目标节点的并行执行；它们的输出通过状态归约器合并。这就是 LangGraph 表达编排器-工作者模式而无需线程原语的方式。

### 子图

一个编译的图可以是另一个图中的节点。外部图看到一个节点；内部图有自己的状态和自己的检查点。这就是团队构建监督者-工作者代理的方式：监督者图将用户意图路由到每个领域的工作子图。

## 构建它

### 步骤 1：状态和节点

```python
from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

def agent_node(state: State) -> dict:
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

def should_continue(state: State) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END

tool_node = ToolNode(tools=[search_web, read_file])

graph = StateGraph(State)
graph.add_node("agent", agent_node)
graph.add_node("tools", tool_node)
graph.set_entry_point("agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")

app = graph.compile(checkpointer=MemorySaver())
```

`add_messages` 是使消息列表累积而非覆盖的归约器。忘记它是最常见的 LangGraph bug。

### 步骤 2：用线程运行

```python
config = {"configurable": {"thread_id": "user-42"}}
for event in app.stream(
    {"messages": [HumanMessage("find the Anthropic headquarters address")]},
    config,
    stream_mode="updates",
):
    print(event)
```

每个更新是一个字典 `{node_name: state_delta}`。你的前端可以将这些流式传输到 UI，让用户看到"代理正在思考…调用 search_web…获取结果…回答中。"

### 步骤 3：添加人机交互中断

标记节点以便执行在运行前暂停。

```python
app = graph.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["tools"],  # 在每次工具调用前暂停
)

state = app.invoke({"messages": [HumanMessage("delete the production database")]}, config)
# state["__interrupt__"] 已设置。检查提议的工具调用。
# 如果批准：
from langgraph.types import Command
app.invoke(Command(resume=True), config)
# 如果拒绝：写入拒绝消息并恢复
app.update_state(config, {"messages": [AIMessage("Blocked by human reviewer.")]})
```

状态、检查点和线程都跨中断持久化。执行期间没有任何东西在内存中。

### 步骤 4：用于调试的时间旅行

```python
history = list(app.get_state_history(config))
for snapshot in history:
    print(snapshot.values["messages"][-1].content[:80], snapshot.config)

# 从之前的检查点分叉
target = history[3].config  # 回退三步
for event in app.stream(None, target, stream_mode="values"):
    pass  # 从该点向前回放
```

传入 `None` 作为输入从给定检查点回放；传入一个值会在恢复前将其作为更新追加到该检查点的状态。这就是你重现一次糟糕的代理运行而不重新运行整个对话的方式。

### 步骤 5：为生产替换检查器

```python
from langgraph.checkpoint.postgres import PostgresSaver

with PostgresSaver.from_conn_string("postgresql://...") as checkpointer:
    checkpointer.setup()
    app = graph.compile(checkpointer=checkpointer)
```

SQLite、Redis 和 Postgres 已发布。`MemorySaver` 用于测试。任何需要跨重启持久化的东西都需要真正的存储。

## 技能

> 你将代理构建为图，而不是 `while True` 循环。

在你使用 LangGraph 之前，做一个 60 秒设计：

1. **命名节点。** 每个离散决策或有副作用的动作是一个节点。"代理思考"、"工具运行"、"审阅者批准"、"响应流式传输"。如果你无法列出它们，任务还不是代理形态。
2. **声明状态。** 最小的 TypedDict，每个列表字段有归约器。不要把所有东西塞进 `messages`；将特定任务字段（工作 `plan`、`budget` 计数器、`retrieved_docs` 列表）提升到顶层。
3. **画边。** 除非下一步依赖模型输出，否则用静态。每个条件边需要一个带命名分支的路由器函数。
4. **预先选择检查器。** 测试用 `MemorySaver`，其他一切用 Postgres/Redis/SQLite。不要在没有检查器的情况下发布——没有检查器意味着没有恢复、没有中断、没有时间旅行。
5. **在工具运行前决定中断，而不是之后。** 审批放在进入有副作用节点的边上，这样你可以在造成伤害前取消；验证放在模型输出的边上，这样你可以廉价地拒绝错误调用。
6. **默认流式传输。** UI 用 `mode="updates"`，模型节点内的 token 级流式传输用 `mode="messages"`，评估期间的完整快照用 `mode="values"`。

拒绝发布没有检查器的 LangGraph 代理。拒绝发布在副作用*之后*中断的代理。拒绝发布没有 `add_messages` 作为归约器的 `messages` 字段。

## 练习

1. **简单。** 用计算器工具和网络搜索工具实现上面的四节点 ReAct 图。验证 `list(app.get_state_history(config))` 对两轮对话至少返回四个检查点。
2. **中等。** 添加一个在 `agent` 之前运行的 `planner` 节点，将结构化 `plan: list[str]` 写入状态。让 `agent` 标记计划步骤为完成。如果 `plan` 在检查点恢复时丢失（错误的归约器），则测试失败。
3. **困难。** 构建一个监督者图，使用 `Send` 在三个子图（`researcher`、`writer`、`reviewer`）之间路由。每个子图有自己的状态和检查器。在外部图上添加 `interrupt_before=["writer"]`，以便人工可以审批研究摘要。确认从之前检查点的时间旅行只重运行分叉的分支。

## 关键术语

| 术语 | 人们怎么说 | 它的实际含义 |
|------|-----------|-------------|
| StateGraph | "LangGraph 图" | 你在编译前添加节点和边的构建器对象。 |
| Reducer | "字段如何合并" | 当节点返回该字段的更新时应用的函数 `(old, new) -> merged`；默认是覆盖，`add_messages` 追加。 |
| Thread | "对话 ID" | 为一个会话范围所有检查点的 `thread_id` 字符串。 |
| Checkpoint | "暂停的状态" | 节点转换后完整图状态的持久化快照，以 `(thread_id, checkpoint_id)` 为键。 |
| Interrupt | "暂停等待人工" | `interrupt_before` / `interrupt_after` 在节点边界停止执行；用 `Command(resume=...)` 恢复。 |
| Time-travel | "从之前的步骤分叉" | `graph.invoke(None, config_with_old_checkpoint_id)` 从该检查点向前回放。 |
| Send | "并行子图派发" | 节点可以返回的构造器，生成目标节点的 N 个并行执行。 |
| Subgraph | "编译的图作为节点" | 用作另一个图中节点的编译 StateGraph；保留自己的状态范围。 |

## 延伸阅读

- [LangGraph 文档](https://langchain-ai.github.io/langgraph/) — StateGraph、归约器、检查器和中断的权威参考。
- [LangGraph 概念：状态、归约器、检查器](https://langchain-ai.github.io/langgraph/concepts/low_level/) — 本课程使用的心理模型，直接来自源码。
- [LangGraph 持久化和检查点](https://langchain-ai.github.io/langgraph/concepts/persistence/) — Postgres/SQLite/Redis 存储、检查点命名空间和线程 ID 的细节。
- [LangGraph 人机交互](https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/) — `interrupt_before`、`interrupt_after`、`Command(resume=...)` 和编辑状态模式。
- [Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models" (ICLR 2023)](https://arxiv.org/abs/2210.03629) — 每个 LangGraph 代理实现的模式；阅读了解推理追踪原理。
- [Anthropic — 构建有效代理 (2024 年 12 月)](https://www.anthropic.com/research/building-effective-agents) — 优先选择哪些图形状（链、路由器、编排器-工作者、评估器-优化器）以及何时使用。
- Phase 11 · 09 (函数调用) — 每个 LangGraph 代理节点复用的工具调用原语。
- Phase 11 · 14 (模型上下文协议) — 通过 MCP 适配器插入 LangGraph `ToolNode` 的外部工具发现。
- Phase 11 · 17 (代理框架权衡) — 何时选择 LangGraph 而非 CrewAI、AutoGen 或 Agno。