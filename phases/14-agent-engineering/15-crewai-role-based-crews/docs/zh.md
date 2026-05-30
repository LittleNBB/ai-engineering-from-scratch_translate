# CrewAI：基于角色的团队与工作流

> CrewAI 是 2026 年基于角色的多 Agent 框架。四个原语：Agent、Task、Crew、Process。两种顶层形态：Crews（自主的、基于角色的协作）和 Flows（事件驱动的、确定性的）。文档直言不讳："对于任何生产就绪的应用，从 Flow 开始。"

**类型：** Learn + Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 12（Workflow Patterns）、Phase 14 · 14（Actor Model）
**时间：** ~75 分钟

## 学习目标

- 说出 CrewAI 的四个原语（Agent、Task、Crew、Process）及其各自的职责。
- 区分 Sequential、Hierarchical 和计划中的 Consensus 流程；按工作负载选择。
- 区分 Crews（自主的、基于角色的）和 Flows（事件驱动的、确定性的），并解释文档的生产推荐。
- 使用 `@tool` 装饰器和 `BaseTool` 子类接线工具；推理结构化输出 vs 自由文本。
- 说出 CrewAI 的四种记忆类型及其各自的价值场景。
- 用标准库实现一个三 Agent 团队（研究员、作者、编辑）来产出简报。
- 识别 CrewAI 的三种失败模式：提示膨胀、管理者 LLM 开销、脆弱的交接。

## 问题

采用多 Agent 框架的团队撞上了同一面墙。"自主协作"在演示中听起来很棒。然后客户提交了一个 bug，你需要确定性重放。或者财务问一个 LLM 路由的团队每次运行成本多少。或者值班人员需要知道哪个 Agent 在凌晨 3 点卡住了。

自由形态的 LLM 路由团队无法干净地回答这些问题。纯 DAG 能回答所有问题，但失去了头脑风暴 Agent 需要的探索性形状。

CrewAI 的分离坦诚面对了这种权衡。Crews 用于协作的、基于角色的、探索性的工作。Flows 用于事件驱动的、代码拥有的、可审计的生产。同一框架，两种形状，按场景选择。

## 核心概念

### 四个原语

CrewAI 的接口很小。记住这个，其余都是配置。

- **Agent。** `role + goal + backstory + tools + (可选) llm`。背景故事是承重的。它塑造语气、判断、Agent 何时停止。工具是 Agent 可以调用的函数（更多见下文）。
- **Task。** `description + expected_output + agent + (可选) context + (可选) output_pydantic`。可复用的工作单元。`expected_output` 是契约。`context` 列出其输出被传入的上游任务。`output_pydantic` 强制结构化形状。
- **Crew。** 容器。拥有 `agents` 列表、`tasks` 列表、`process`，以及可选的 `memory` + `verbose` + `manager_llm` 设置。
- **Process。** 执行策略。Sequential、Hierarchical、Consensus（计划中）。决定运行的形状。

Agent 不能直接看到彼此。Task 引用 Agent。Crew 对 Task 排序。Process 决定谁选择下一个 Task。这就是全部心智模型。

> **验证于** CrewAI 0.86（2026-05）。新版本可能重命名或合并流程类型；依赖特定形状前请检查 [CrewAI Processes 文档](https://docs.crewai.com/concepts/processes)。

### Sequential vs Hierarchical vs Consensus

- **Sequential。** Task 按声明顺序运行。Task N 的输出作为 `context` 对 Task N+1 可用。最低成本。最可预测。当顺序固定时使用。
- **Hierarchical。** 一个管理者 Agent（单独的 LLM 调用）在专家之间路由。CrewAI 从你的 `manager_llm` 配置或默认值生成管理者。管理者每轮选择下一个 Task，可以拒绝或重新路由。当你有四个或更多专家且顺序真正取决于先前输出时使用。
- **Consensus。** 计划中，目前未在公共 API 中实现。文档为未来的基于投票的流程保留了名称。今天不要依赖它。

Hierarchical 在每个专家调用之上添加了每轮的 LLM 调用（管理者）。五步运行中 token 成本可能翻三倍。仅在需要路由时才为此付费。

### Crews vs Flows

这是 2026 年文档首先提出的框架。

- **Crew。** LLM 驱动的自主性。框架在运行时选择形状。适合：研究、头脑风暴、初稿、路径本身是答案一部分的地方。难以重放。难以测试。原型开发成本低。
- **Flow。** 你拥有的事件驱动图。`@start` 标记入口。`@listen(topic)` 标记当另一个步骤发出该主题时触发的步骤。每个步骤是普通 Python（可以在内部调用 Crew）。适合：生产。可观察。可测试。确定性。

文档 2026 年的生产推荐：从 Flow 开始。当自主性值得其成本时，在 Flow 步骤内部将 Crews 作为 `Crew.kickoff()` 调用折叠进来。Flow 给你审计轨迹，Crew 给你探索能力。组合，而非选择。

### 工具集成

三种方式给 Agent 工具。选择最适合的最简单方式。

1. **`@tool` 装饰器。** 纯函数变成工具。签名是 schema；文档字符串是 LLM 看到的描述。最适合一次性辅助函数。

   ```python
   from crewai.tools import tool

   @tool("Search the web")
   def search(query: str) -> str:
       """Return top results for the query."""
       return run_search(query)
   ```

2. **`BaseTool` 子类。** 基于类的工具，带显式 args schema、异步支持、重试。当工具有状态（客户端、缓存）或需要结构化参数时使用。

   ```python
   from crewai.tools import BaseTool
   from pydantic import BaseModel

   class SearchArgs(BaseModel):
       query: str
       limit: int = 10

   class SearchTool(BaseTool):
       name = "web_search"
       description = "Search the web and return top results."
       args_schema = SearchArgs

       def _run(self, query: str, limit: int = 10) -> str:
           return self.client.search(query, limit=limit)
   ```

3. **内置工具包。** CrewAI 提供第一方适配器：`SerperDevTool`、`FileReadTool`、`DirectoryReadTool`、`CodeInterpreterTool`、`RagTool`、`WebsiteSearchTool`。一个 import 即可接线。

结构化输出使用 Pydantic。在 Task 上传 `output_pydantic=MyModel`。CrewAI 根据模型验证 LLM 响应，要么强制转换要么重试。配合紧凑的 `expected_output` 字符串使用。自由文本输出适合草稿；结构化输出是下游 Flows 可以消费的。

### 记忆钩子

CrewAI 开箱即用提供四种记忆类型。它们可以组合：一个 Crew 可以同时启用所有四种。

> **验证于** CrewAI 0.86（2026-05）。近期版本通过统一的 `Memory` 系统路由所有内容，该系统包装了这四个存储。下面的概念模型仍然成立，但公共类接口可能在新版本中合并为单一 `Memory` 入口点；请检查 [CrewAI 记忆文档](https://docs.crewai.com/concepts/memory) 获取当前 API。

- **短期记忆。** 单次运行内的对话缓冲区。运行结束时清除。
- **长期记忆。** 跨运行持久化。存储在向量数据库（默认 Chroma，可替换）。通过与当前任务的相似度检索。
- **实体记忆。** 每个实体的事实。"客户 X 使用企业计划。"按键而非相似度索引。跨运行存活。
- **上下文记忆。** 组装时检索。在 Agent 需要的时刻拉取相关记忆，而非预加载。

在 Crew 上用 `memory=True` 或每类型配置启用。由你配置的 embeddings 提供商支持（默认 OpenAI，可替换为本地）。记忆是 CrewAI 对比更薄框架体现价值的地方之一；纯 LangGraph 需要你自己接线每个。

### 何时适合 CrewAI

- 三到六个带命名角色和协作工作流的 Agent。起草、审查、规划、头脑风暴。
- LLM 对下一步的判断本身有价值的路由（Hierarchical）。
- 团队更喜欢读 `role + goal + backstory` 而非图定义的地方。

### 何时不适合 CrewAI

- 严格排序的确定性 DAG。使用 LangGraph（第 13 课）。图的形状是正确的抽象；CrewAI 的角色框架是摩擦。
- 亚秒级延迟预算。Hierarchical 添加往返。即使 Sequential 也序列化包含背景故事和先前输出的提示。
- 单 Agent 循环。跳过框架；Agent 循环（第 1 课）加工具注册表更短。

第 17 课（Agent 框架权衡）在矩阵中列出了这一点。简短版本：CrewAI 位于"协作式基于角色"的角落。

### 依赖形状

独立于 LangChain。Python 3.10 到 3.13。使用 `uv`。Star 数：见 [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI)（2026-05 快照）。AWS Bedrock 集成已文档化；供应商基准报告在 QA 工作负载上比 LangGraph 有大幅加速，但方法论（数据集、硬件、评估指标）未发布，因此将框架供应商数字视为方向性参考。

### 这个模式出错的地方

- **背景故事导致提示膨胀。** 每个 Agent 2000 字的背景故事加五人团队在第一次工具调用前就烧完了上下文预算。将背景故事控制在 200 字以内。跨 Agent 复用短语；不要将公司风格重复五遍。
- **管理者 LLM token 税。** Hierarchical 流程在每个专家调用前添加一个管理者 LLM 调用。五人团队中这是六次 LLM 调用而非五次，且管理者调用携带完整任务列表加先前输出。除非路由依赖输出，否则切换到 Sequential。
- **脆弱的交接。** Task N 的 `expected_output` 是"大纲"。Task N+1 将其作为 `context` 读取并尝试解析三个部分。LLM 产出了四个。下游 Agent 即兴发挥。在 Task N 上用 `output_pydantic` 修复，这样 Task N+1 读取类型化对象而非自由文本。
- **Crew 当产品。** 自由形态 Crew 不加 Flow 包装就发布到生产。输出变异性高；重放不可能；值班人员无法将坏运行与好运行对比。用 Flow 包装。

## 构建它

`code/main.py` 用标准库实现了两种形态加一个三 Agent 团队。

形态：

- `Agent`、`Task` 数据类匹配 CrewAI 的接口。
- `SequentialCrew.kickoff(inputs)` 按声明顺序运行任务，将输出作为 `context` 传递。
- `HierarchicalCrew.kickoff(topic)` 添加一个管理者 Agent 每轮选择下一个专家，在"done"时停止。
- `Flow` 带 `@start` 和 `@listen(topic)` 装饰器、一个微小事件循环和轨迹。
- `tool(name)` 装饰器镜像 CrewAI 的 `@tool` 形状。
- `Memory` 带 `short_term`、`long_term`、`entity` 存储；模拟相似度使用 numpy。
- 模拟 LLM 响应是基于角色加输入前缀的硬编码字符串。无网络。确定性。

具体演示：研究员、作者、编辑团队产出关于"2026 年 Agent 工程"的简报。研究员拉取（模拟的）来源。作者起草。编辑精简。同一团队通过 Flow 运行以展示确定性形状。

运行它：

```bash
python3 code/main.py
```

轨迹覆盖：顺序团队通过 `context` 传递输出、层级团队带管理者选择（研究员、作者、编辑，然后"done"）、Flow 以显式主题（`researched`、`drafted`、`edited`）运行相同三步、通过 `@tool` 路由的工具调用、以及跨两次 kickoff 存活的长期记忆。

Crew 轨迹是流动的；管理者原则上可以重新排序。Flow 轨迹是固定的。这个选择就是本课的核心。

## 使用它

- **CrewAI Flow** 用于生产。即使 Flow 是一步调用 `Crew.kickoff()`。Flow 提供审计边界。
- **CrewAI Crew（Sequential）** 用于清晰排序的协作工作，尤其是初稿和审查循环。
- **CrewAI Crew（Hierarchical）** 当路由依赖输出且你有四个或更多专家时。
- **LangGraph**（第 13 课）用于显式状态机、持久恢复、严格排序。
- **AutoGen v0.4**（第 14 课）用于 Actor 模型并发和故障隔离。
- **OpenAI Agents SDK**（第 16 课）用于 OpenAI 优先的产品，带交接和护栏。
- **Claude Agent SDK**（第 17 课）用于 Claude 优先的产品，带子 Agent 和会话存储。

## 发布它

`outputs/skill-crew-or-flow.md` 为任务选择 Crew vs Flow 并脚手架最小实现。硬拒绝：Crew 无背景故事、Flow 无显式主题、Hierarchical 少于三个专家。

## 陷阱

- **背景故事当调味料。** 它塑造输出。每个 Agent 测试三个变体；方差是真实的。选一个，冻结。
- **跳过 `expected_output`。** 没有每个任务的契约，下游任务接收 LLM 产出的任何内容。Crew 运行了；审计失败。
- **记忆始终开启。** 每次运行写入长期记忆。向量数据库增长。检索变嘈杂。将写入限定到事实持久的任务。
- **管理者提示漂移。** Hierarchical 的管理者提示是隐式的。如果路由变得奇怪，在 verbose 模式中转储并阅读。
- **Crew 中的工具副作用。** Crew 可以比预期更多次调用工具。POST、DELETE、支付属于 Flow 步骤，绝非 Crew 工具。

## 练习

1. 将 Sequential 团队转换为 Flow。计算变异性降低的接触点。注意可读性降低的地方。
2. 给团队添加实体记忆：关于客户的事实跨 kickoff 持存。验证检索拉取了正确的实体。
3. 实现一个 Hierarchical 流程，管理者拒绝路由到编辑，直到作者的输出至少有三段。追踪重试。
4. 为（模拟的）Web 搜索接线一个 `BaseTool` 子类。比较轨迹形状与 `@tool` 装饰器版本。
5. 给编辑任务添加 `output_pydantic=Brief`，其中 `Brief` 有 `title`、`summary`、`sections`。让作者任务输出一次格式错误的 JSON；在轨迹中验证 CrewAI 的重试行为。
6. 阅读 CrewAI 文档介绍。将玩具代码移植到真实的 `crewai` API。标准库版本跳过了哪些保证？
7. 将 AgentOps 或 Langfuse（第 24 课）接线到真实运行。你在标准库版本中遗漏了哪些轨迹？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Agent | "角色" | Role + goal + backstory + tools |
| Task | "工作单元" | 描述 + 预期输出 + 负责人 + 可选结构化输出 |
| Crew | "Agent 团队" | Agent + Task + Process 的容器 |
| Process | "执行策略" | Sequential / Hierarchical / Consensus（计划中） |
| Flow | "确定性工作流" | 事件驱动的、代码拥有的、可测试的 |
| Backstory | "角色提示" | Agent 的语气和判断塑造器 |
| `@tool` | "函数工具" | 将函数变成 Agent 可调用工具的装饰器 |
| `BaseTool` | "类工具" | 基于类的工具，带 args schema、重试、异步支持 |
| Entity memory | "每实体事实" | 限定到客户/账户/问题的记忆 |
| Long-term memory | "跨运行记忆" | 向量支持的、跨 kickoff 存活的记忆 |
| Contextual memory | "即时检索" | 在 Agent 需要时刻拉取的记忆 |
| Manager LLM | "路由器 Agent" | Hierarchical 流程中选择下一个任务的额外 LLM |
| `expected_output` | "任务契约" | 告诉 Agent（和审计）返回什么形状的字符串 |

## 延伸阅读

- [CrewAI 文档介绍](https://docs.crewai.com/en/introduction)：概念和推荐的生产路径
- [CrewAI Flows 指南](https://docs.crewai.com/en/concepts/flows)：事件驱动形状、`@start`、`@listen`
- [CrewAI 工具参考](https://docs.crewai.com/en/concepts/tools)：`@tool`、`BaseTool`、内置工具包
- [CrewAI 记忆](https://docs.crewai.com/en/concepts/memory)：短期、长期、实体、上下文
- [Anthropic, Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)：多 Agent 何时有帮助，何时没有
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)：状态机替代方案