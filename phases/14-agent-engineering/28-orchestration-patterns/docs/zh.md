# 编排模式（Orchestration Patterns）：Supervisor、Swarm、Hierarchical

> 2026 年的框架中反复出现四种编排模式：supervisor-worker（主管-工作者）、swarm / peer-to-peer（群体/点对点）、hierarchical（层级式）、debate（辩论式）。Anthropic 的建议："关键在于构建适合你需求的系统。"从简单开始；仅当单个智能体加五种工作流模式不够用时，才添加拓扑。

**类型：** Learn + Build
**语言：** Python（标准库）
**前置课程：** Phase 14 · 12（Workflow Patterns），Phase 14 · 25（Multi-Agent Debate）
**时间：** ~60 分钟

## 学习目标

- 列出四种反复出现的编排模式及其适用场景。
- 描述 2026 年 LangChain 的建议：基于工具调用的监督 vs 使用 Supervisor 库。
- 解释 Anthropic 的"构建适合的系统"原则及其如何决定拓扑选择。
- 在标准库中使用同一脚本化 LLM 实现全部四种模式。

## 问题背景

团队往往在真正需要之前就急于使用"多智能体"。四种模式在各框架中反复出现；一旦你能命名它们，就能选择正确的模式 — 或者完全跳过拓扑。

## 核心概念

### Supervisor-worker（主管-工作者）

- 一个中央路由 LLM 将任务分派给专家智能体。
- 决策：回到自身循环、交给专家、终止。
- 专家之间不直接通信；所有路由都经过主管。

框架实现：LangGraph `create_supervisor`、Anthropic orchestrator-workers、CrewAI Hierarchical Process。

**2026 年 LangChain 建议：** 通过直接工具调用实现监督，而非使用 `create_supervisor`。这样可以提供更精细的上下文工程控制 — 你可以精确决定每个专家看到什么。

### Swarm / Peer-to-peer（群体/点对点）

- 智能体通过共享工具表面直接交接。
- 无中央路由器。
- 延迟低于 Supervisor（更少的跳转）。
- 更难推理（没有单一控制点）。

框架实现：LangGraph swarm 拓扑、OpenAI Agents SDK handoffs（当所有智能体都可以相互交接时）。

### Hierarchical（层级式）

- 主管管理子主管，子主管管理工作者。
- 在 LangGraph 中实现为嵌套子图；在 CrewAI 中实现为嵌套 Crew。
- 以运营复杂性为代价，扩展到大规模智能体群体。

适用场景：当单个主管的上下文预算无法容纳所有专家的描述时。

### Debate（辩论式）

- 并行提议者 + 迭代交叉批评（第 25 课）。
- 严格来说不是编排 — 更像是验证 — 但作为拓扑选择出现在框架中。

### CrewAI Crew vs Flow

CrewAI 将两种部署模式形式化：

- **Flow** — 用于确定性事件驱动自动化（生产环境的推荐起点）。
- **Crew** — 用于自主的角色协作。

这与上述四种模式正交，但映射到拓扑上：Flow 通常是 Supervisor 或 Hierarchical；Crew 通常是带 LLM 路由器的 Supervisor。

### Anthropic 的指导原则

"在 LLM 领域，成功不在于构建最复杂的系统。关键在于构建适合你需求的系统。"

决策顺序：

1. 单个智能体 + 工作流模式（第 12 课）— 从这里开始。
2. Supervisor-worker — 当你有 2-4 个专家时。
3. Swarm — 当延迟比推理清晰度更重要时。
4. Hierarchical — 仅当主管上下文预算不足时。
5. Debate — 当准确率比成本更重要时。

### 这种模式的常见陷阱

- **拓扑优先思维。** 在明确多智能体解决什么问题之前就说"我们需要多智能体"。
- **Swarm 中的来回跳转。** A -> B -> A -> B。使用跳转计数器。
- **虚假层级。** 为了"企业级"设三层；实际只有两个团队。应简化。

## 动手实现

`code/main.py` 使用同一脚本化 LLM 在标准库中实现全部四种模式：

- `Supervisor` — 中央路由器。
- `Swarm` — 直接交接的点对点模式。
- `Hierarchical` — 主管的主管。
- `Debate` — 并行提议者 + 批评。

每种模式处理相同的三意图任务（退款 / Bug / 销售）。追踪形状各不相同。

运行：

```
python3 code/main.py
```

输出：每种模式的追踪 + 操作数。Supervisor 最清晰；Swarm 最短；Hierarchical 最深；Debate 最昂贵。

## 实践应用

- **LangGraph** — 用于 Supervisor 和 Hierarchical（嵌套子图）。
- **OpenAI Agents SDK** — 用于 handoffs-as-tools（Supervisor 形态）。
- **CrewAI Flow** — 用于生产环境的确定性流程。
- **自定义方案** — 用于 Debate 或需要精确控制的场景。

## 产出物

`outputs/skill-orchestration-picker.md` 选择一种拓扑并实现它。

## 练习

1. 将 Supervisor-worker 转换为 Swarm，移除路由器。什么会出错？什么会改善？
2. 为 Swarm 添加跳转计数器：超过 3 次交接后拒绝。能否捕获 A->B->A 的来回跳转？
3. 为 12 个专家的领域构建一个两层层级系统。没有嵌套时，上下文预算在哪里不足？
4. 在生产级负载上对比四种模式的性能。哪种在哪项指标上最优（延迟、成本、准确率、可调试性）？
5. 阅读 Anthropic 的"Building Effective Agents"文章。将你的每个生产流程映射到四种模式之一。是否有不完全匹配的？

## 关键术语

| 术语 | 通俗说法 | 实际含义 |
|------|----------|----------|
| Supervisor-worker（主管-工作者） | "路由器 + 专家" | 中央 LLM 分派给专家；专家之间不直接通信 |
| Swarm（群体） | "点对点" | 通过共享工具直接交接；无中央路由器 |
| Hierarchical（层级式） | "主管的主管" | 用于大规模群体的嵌套子图 |
| Debate（辩论式） | "提议者 + 批评" | 并行提议者，交叉批评（第 25 课） |
| Tool-call-based Supervision（基于工具调用的监督） | "无库的 Supervisor" | 通过直接工具调用实现 Supervisor 以获得上下文控制 |
| Crew | "自主团队" | CrewAI 的角色协作模式 |
| Flow | "确定性工作流" | CrewAI 的事件驱动生产模式 |

## 延伸阅读

- [Anthropic, Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — 五种模式 + 智能体 vs 工作流
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) — Supervisor、Swarm、Hierarchical
- [CrewAI docs](https://docs.crewai.com/en/introduction) — Crew vs Flow
- [Du et al., Society of Minds (arXiv:2305.14325)](https://arxiv.org/abs/2305.14325) — 辩论模式