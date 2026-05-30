# 多智能体辩论与协作（Multi-Agent Debate and Collaboration）

> Du 等人（ICML 2024，"Society of Minds"）运行 N 个模型实例，各自独立提出答案，然后在 R 轮中迭代地相互批评以达成收敛。提升了事实准确性、规则遵循和推理能力。稀疏拓扑（Sparse Topology）在 Token 成本上优于全连接拓扑（Full Mesh）。

**类型：** Learn + Build
**语言：** Python（标准库）
**前置课程：** Phase 14 · 12（Workflow Patterns），Phase 14 · 05（Self-Refine and CRITIC）
**时间：** ~60 分钟

## 学习目标

- 解释辩论协议：N 个提议者，R 轮，收敛到共享答案。
- 描述为什么辩论能提升事实准确性、规则遵循和推理能力。
- 解释稀疏拓扑：并非每个辩论者都需要看到其他所有人的内容。
- 实现一个基于脚本化 LLM 的标准库辩论，包含全连接和稀疏变体；测量 Token 成本与准确率的关系。

## 问题背景

Self-Refine（第 05 课）是一个模型自我批评 — 存在群体思维（Groupthink）风险。CRITIC（第 05 课）基于外部工具进行批评 — 但外部工具不总是可用。辩论引入了第三种模式：多个实例、交叉批评、通过分歧达成收敛。

## 核心概念

### Society of Minds（Du 等人，ICML 2024）

- N 个模型实例独立对同一问题提出答案。
- 在 R 轮中，每个模型阅读其他模型的提议并进行批评。
- 模型根据批评更新自己的答案。
- R 轮结束后，返回收敛的答案。

原始实验由于成本考虑使用 N=3，R=2。在难题上（MMLU、GSM8K、Chess Move Validity、传记生成），增加智能体数量和轮次可提升准确率。

跨模型组合优于单一模型辩论：ChatGPT + Bard 的组合 > 任一单独模型。

### 稀疏拓扑（Sparse Topology）

"Improving Multi-Agent Debate with Sparse Communication Topology"（arXiv:2406.11776，2024-2025）证明全连接辩论并非总是最优。稀疏拓扑（星型、环型、中心辐射型）可以在更低的 Token 成本下匹配准确率。每个辩论者只看到部分同伴。

含义：

- 全连接 N=5，R=3 = 5 × 3 = 15 个提议，每个阅读 4 个同伴 = 60 次批评操作。
- 星型 N=5，R=3（1 个中心 + 4 个辐射端）= 15 个提议，辐射端只阅读中心 = 12 次批评操作。

### 辩论何时有效

- **事实准确性。** N 个独立提议，交叉验证减少幻觉。
- **规则遵循。** 国际象棋走法合法性 — 一个模型遗漏规则，其他模型能捕获。
- **开放式推理。** 多种视角缩小正确答案范围。

### 辩论何时无效

- **延迟敏感的 UX。** N × R 轮串行延迟可能是你无法承受的。
- **成本敏感的规模化。** 每个问题 N × R 个 Token。
- **简单事实查询。** 一次查询比五轮辩论更便宜。

### 2026 年的实际应用

- **Anthropic orchestrator-workers**（第 12 课）— 带综合步骤的辩论变体。
- **LangGraph supervisor**（第 13 课）— 中央路由器 + 专家智能体可将辩论实现为一个节点。
- **OpenAI Agents SDK**（第 16 课）— 智能体相互交接以进行迭代批评。
- **多智能体评估** — 将辩论 + 评估器-优化器配对以获取评估信号。

### 这种模式的常见陷阱

- **收敛崩溃（Convergence Collapse）。** 所有智能体都收敛到第一个错误答案。通过强制分歧轮次来缓解。
- **中心节点失败。** 在星型拓扑中，坏的中心节点会污染所有人。轮换中心或使用多个中心。
- **提示同质化（Prompt Homogenization）。** 所有智能体使用相同提示；产生相同答案。使用多样化提示和/或不同模型。

## 动手实现

`code/main.py` 实现了标准库辩论：

- `Debater` 类（带每个辩论者观点漂移的脚本化 LLM）。
- `FullMeshDebate` 和 `SparseDebate` 运行器。
- 三个问题：一个事实类、一个规则类、一个推理类。
- 指标：收敛答案、收敛轮次、总批评操作数。

运行：

```
python3 code/main.py
```

输出：每种协议的准确率和成本；稀疏拓扑在 2/3 的问题上以更低成本匹配全连接。

## 实践应用

- **Anthropic orchestrator-workers** — 简单的 2-3 个工作者辩论。
- **LangGraph** — 带检查点的有状态多轮辩论。
- **自定义方案** — 用于研究或特定的正确性保证。

## 产出物

`outputs/skill-debate.md` 生成一个多智能体辩论的脚手架代码，支持可配置的拓扑、N、R 和收敛规则。

## 练习

1. 实现"强制分歧"规则：在第 1 轮中，每个辩论者必须产生不同的提议。测量对收敛速度的影响。
2. 添加置信度加权聚合：辩论者返回（答案、置信度）；聚合器按置信度加权。是否有帮助？
3. 将一个"智能体"替换为带有不同观点的脚本化 LLM。异质性能否提升准确率？
4. 测量全连接 vs 稀疏拓扑在 3 个问题上的 Token 成本。绘制成本 vs 准确率图。
5. 阅读 Society of Minds 论文。将模拟器扩展到 N=5，R=3。什么会出错？什么会变好？

## 关键术语

| 术语 | 通俗说法 | 实际含义 |
|------|----------|----------|
| Debate（辩论） | "多智能体批评" | N 个提议者，R 轮交叉批评，达成收敛 |
| Full Mesh（全连接） | "每个人都读每个人的" | 每个辩论者每轮阅读所有同伴 |
| Sparse Topology（稀疏拓扑） | "有限的同伴视野" | 辩论者只阅读部分同伴 |
| Hub-and-spoke（中心辐射型） | "星型拓扑" | 一个中心辩论者，N-1 个辐射端只阅读中心 |
| Convergence（收敛） | "达成一致" | 辩论者收敛到共享答案 |
| Society of Minds | "Du 等人的辩论论文" | ICML 2024 多智能体辩论方法 |

## 延伸阅读

- [Du et al., Society of Minds (arXiv:2305.14325)](https://arxiv.org/abs/2305.14325) — 标准多智能体辩论
- [Sparse Communication Topology (arXiv:2406.11776)](https://arxiv.org/abs/2406.11776) — 稀疏拓扑结果
- [Anthropic, Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — orchestrator-workers 作为辩论变体
- [Madaan et al., Self-Refine (arXiv:2303.17651)](https://arxiv.org/abs/2303.17651) — 单模型自我批评的对应方案