# ReWOO 与 Plan-and-Execute：解耦式规划

> ReAct 在一个流中交替思考和行动。ReWOO 将它们分离：先制定一个完整的计划，然后执行。token 用量减少 5 倍，HotpotQA 准确率提升 +4%，并且可以将规划器蒸馏到 7B 模型中。Plan-and-Execute 将其泛化；Plan-and-Act 将其扩展到 Web 导航。

**类型：** Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 01（Agent Loop）
**时间：** ~60 分钟

## 学习目标

- 解释为什么 ReWOO 的 Planner / Worker / Solver 分离比 ReAct 的交错循环更节省 token 且更健壮。
- 实现一个计划 DAG、一个按依赖顺序执行的执行器，以及一个组合 worker 输出的求解器 —— 全部使用标准库。
- 使用 2026 年"五种工作流模式"框架（Anthropic）判断一个任务应该用"先计划再执行"还是交错 ReAct。
- 识别何时需要 Plan-and-Act 的合成计划数据来处理长周期的 Web 或移动任务。

## 问题

ReAct 的交错思考-行动-观察循环简单灵活，但每次工具调用都必须携带完整的先前上下文 —— 包括每一次之前的思考。Token 使用量随深度二次增长。更糟的是：当一个工具在循环中途失败时，模型必须从错误观察中重新推导整个计划。

ReWOO（Xu 等人，arXiv:2305.18323，2023 年 5 月）注意到了这一点并做了一个赌注：预先规划整个计划，并行获取证据，最后组合答案。一次 LLM 调用进行规划，N 次工具调用获取证据（可以并行），一次 LLM 调用进行求解。这种权衡是用更少的灵活性（计划是静态的）换来更好的 token 效率和更清晰的故障模式。

## 核心概念

### 三个角色

```
Planner:  user_question -> [plan_dag]
Workers:  [plan_dag]     -> [evidence]        (tool calls, possibly parallel)
Solver:   user_question, plan_dag, evidence -> final_answer
```

Planner 产生一个 DAG。每个节点命名一个工具、其参数以及它依赖的哪些先前节点（如 `#E1`、`#E2` 的引用）。Worker 按拓扑顺序执行节点。Solver 将所有内容拼接在一起。

### 为什么 token 用量减少 5 倍

ReAct 的提示长度随步骤数线性增长。在第 10 步时，提示包含思考 1 加动作 1 加观察 1 加思考 2 加动作 2 加观察 2，以此类推。每个中间步骤也冗余地包含原始提示。

ReWOO 支付一次 planner 提示（较大）、N 次小的 worker 提示（每次只有工具调用，没有链）和一次 solver 提示。在 HotpotQA 上，论文测量到约 5 倍的 token 减少，同时绝对准确率提升 +4。

### 为什么更健壮

如果在 ReAct 中 worker 3 失败，循环必须在流中推理出错误。在 ReWOO 中，worker 3 返回一个错误字符串；solver 在上下文中看到它，并结合原始计划优雅地降级处理。故障定位是按节点的，而不是按步骤的。

### 规划器蒸馏

论文的第二个结果：因为 planner 不观察 observation，你可以在 175B 教师的 planner 输出上微调一个 7B 模型。小模型负责规划；推理时不需要大模型。这现在是标准做法 —— 许多 2026 年的生产 Agent 使用小规划器和大执行器，或者反过来。

### Plan-and-Execute（LangChain, 2023）

LangChain 团队在 2023 年 8 月的帖子中将 ReWOO 泛化为一个模式名称：Plan-and-Execute。预先的 planner 发出一个步骤列表，executor 运行每个步骤，一个可选的 replanner 可以在观察结果后进行修订。这比 ReWOO 更接近 ReAct（replanner 将 observation 带回规划中），但保留了 token 节省。

### Plan-and-Act（Erdogan 等人，arXiv:2503.09572，ICML 2025）

Plan-and-Act 将该模式扩展到长周期的 Web 和移动 Agent。关键贡献是合成计划数据：一个标注轨迹生成器产生计划显式的训练数据。用于微调规划器模型，使其在 WebArena 类任务上保持 30-50 步以上的工作能力，而单个 ReAct 轨迹在此类任务上会失去连贯性。

### 何时选择哪种

| 模式 | 适用场景 |
|------|---------|
| ReAct | 短任务、未知环境、需要反应式异常处理 |
| ReWOO | 工具已知的结构化任务、token 敏感、可并行化的证据 |
| Plan-and-Execute | 类似 ReWOO，但在部分执行后可重新规划 |
| Plan-and-Act | 长周期（>30 步）、Web/移动/计算机使用 |
| Tree of Thoughts | 搜索值得付出代价（第 4 课） |

Anthropic 2024 年 12 月的指导：从最简单的开始。如果任务是一次工具调用加一个摘要，不要构建 ReWOO。如果任务是一个 40 步的研究任务，不要只用 ReAct。

## 构建它

`code/main.py` 实现了一个玩具 ReWOO：

- `Planner` —— 一个脚本化策略，从提示中发出一个计划 DAG。
- `Worker` —— 通过注册表分发每个节点的工具调用。
- `Solver` —— 脚本化的组合，读取证据并产生最终答案。
- 依赖解析 —— 如 `#E1` 的引用在分发时被替换为先前的 worker 输出。

演示回答了"法国首都的人口是多少，四舍五入到百万？"，使用两步计划：(1) 查找首都，(2) 查找人口，然后求解。

运行它：

```
python3 code/main.py
```

轨迹首先显示完整计划，然后是 worker 结果，然后是 solver 组合。将 token 计数（我们打印粗略的字符计数）与 ReAct 风格的交错运行进行比较 —— ReWOO 在这类结构化任务上获胜。

## 使用它

LangGraph 以配方形式提供 Plan-and-Execute（`create_react_agent` 用于 ReAct，自定义图用于 plan-execute）。CrewAI 的 Flows 直接编码该模式：你预先定义任务，Flow DAG 执行它们。Plan-and-Act 的合成数据方法仍主要处于研究阶段；运行时模式（显式计划 DAG）通过 LangGraph 和 CrewAI Flows 在生产中发布。

## 发布它

`outputs/skill-rewoo-planner.md` 从用户请求生成一个 ReWOO 计划 DAG，给定一个工具目录。它在交给执行器之前验证计划（无环、每个引用都已解析、每个工具都存在）。

## 练习

1. 对独立的计划节点并行化 worker 执行。在一个有 2 个并行组的 6 节点 DAG 上，这给你带来什么收益？
2. 添加一个 replanner 节点，在任何 worker 返回错误时触发。将 ReWOO 变成 Plan-and-Execute 的最小改动是什么？
3. 将 `Planner` 替换为一个小模型（7B 级别），将 `Solver` 保留在前沿模型上。比较端到端质量 —— 分离在哪里失败？
4. 阅读 ReWOO 论文中关于规划器蒸馏的第 4 节。概念性地复现 175B -> 7B 的结果：你需要什么训练数据，如何评分计划质量？
5. 将玩具代码移植到 Plan-and-Act 的轨迹形态：计划是序列而非 DAG。什么权衡发生了变化？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| ReWOO | "不带观察的推理" | 先规划，然后并行获取证据，然后求解 —— 规划提示中没有 observation |
| Plan-and-Execute | "LangChain 的 plan-execute 模式" | 带可选 replanner 节点的 ReWOO |
| Plan-and-Act | "扩展的 plan-execute" | 显式的 planner/executor 分离，带有用于长周期任务的合成计划训练数据 |
| Evidence reference | "#E1, #E2, ..." | 在分发时被替换为先前 worker 输出的计划节点占位符 |
| Planner distillation | "小规划器，大执行器" | 在大教师的 planner 轨迹上微调小模型 |
| Token efficiency | "更少的往返" | 论文中 HotpotQA 上比 ReAct 减少 5 倍 token |
| DAG executor | "拓扑分发器" | 按依赖顺序运行计划节点；每层可并行 |

## 延伸阅读

- [Xu 等人, ReWOO: Decoupling Reasoning from Observations (arXiv:2305.18323)](https://arxiv.org/abs/2305.18323) —— 标准论文
- [Erdogan 等人, Plan-and-Act (arXiv:2503.09572)](https://arxiv.org/abs/2503.09572) —— 使用合成计划的扩展 planner-executor
- [LangGraph Plan-and-Execute tutorial](https://docs.langchain.com/oss/python/langgraph/overview) —— 框架配方
- [Anthropic, Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) —— 选择能工作的最简单模式