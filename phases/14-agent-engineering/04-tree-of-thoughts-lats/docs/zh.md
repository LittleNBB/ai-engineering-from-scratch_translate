# Tree of Thoughts 与 LATS：审慎搜索

> 单条思维链轨迹没有回溯的余地。ToT（Yao 等人，2023）将推理变成一棵树，每个节点都有自评估。LATS（Zhou 等人，2024）在蒙特卡洛树搜索下统一了 ToT、ReAct 和 Reflexion。24 点游戏从 4%（CoT）提升到 74%（ToT）；LATS 在 HumanEval 上达到 92.7% pass@1。

**类型：** Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 01（Agent Loop）、Phase 14 · 03（Reflexion）
**时间：** ~75 分钟

## 学习目标

- 将推理框架化为搜索：节点是"思考"，边是"展开"，值是"有前途程度"。
- 用标准库实现一个 ToT 风格的 BFS 树搜索，带自评估评分。
- 扩展为一个带选择/展开/模拟/回传播的玩具 LATS MCTS 循环。
- 判断搜索何时值得付出 token 倍增的代价（24 点游戏、代码生成），何时单条轨迹就够了（简单问答）。

## 问题

思维链是线性行走。如果第一步错了，后续每一步都在错误的前提上工作。在 24 点游戏（用四个数字通过 + − × ÷ 得到 24）上，GPT-4 CoT 只有 4% 的准确率。模型在早期选错了子表达式，无法恢复。

推理需要的是提出多个候选方案、评估它们、选择有前途的方案，并在出现死胡同时回溯的能力。这就是搜索。Tree of Thoughts 和 LATS 是两种标准表述。

## 核心概念

### Tree of Thoughts（Yao 等人，NeurIPS 2023）

每个节点是一个连贯的中间步骤（"一个思考"）。每个节点可以展开为 K 个子思考。LLM 用评分提示自评估每个节点。搜索探索这棵树 —— BFS、DFS 或 beam search。

```
                     (root: "find 24 from 4 6 4 1")
                    /               |            \
           ("6 - 4 = 2")    ("4 + 1 = 5")    ("4 * 6 = 24")  <- Score: HIGH
              /   \              |                  |
          ...    ...          ...                finish
```

自评估是承重部分。论文展示了三种变体：`sure / likely / impossible` 分类、`1..10` 数值评分、以及候选间投票。三种方法在 24 点游戏上都大幅超越 CoT（GPT-4 从 4% 提升到 74%）。

### LATS（Zhou 等人，ICML 2024）

LATS 在 MCTS 下统一了 ToT、ReAct 和 Reflexion。LLM 扮演三个角色：

- **策略（Policy）**：提出候选的下一步动作（ReAct 风格）。
- **价值函数（Value function）**：给部分轨迹评分（ToT 风格的自评估）。
- **自反思器（Self-reflector）**：在失败时写一条自然语言反思（Reflexion 风格），并用它为未来的模拟重新播种。

环境反馈（观察）混入价值函数，因此搜索由真实的工具结果而非仅仅是模型意见来引导。论文发表时的结果：HumanEval pass@1 92.7% 使用 GPT-4（当时最优），WebShop 平均 75.9 使用 GPT-3.5（接近基于梯度的微调）。

### MCTS 最小化

每次迭代四个阶段：

1. **选择（Select）** — 使用 UCT（树的上置信界）从根走到叶。
2. **展开（Expand）** — 通过策略生成 K 个子节点。
3. **模拟（Simulate）** — 从子节点使用策略进行模拟，用价值函数（或环境奖励）给叶节点评分。
4. **回传播（Backpropagate）** — 沿路径向上更新访问计数和价值估计。

UCT 公式：`Q(s, a) + c * sqrt(ln N(s) / N(s, a))`。第一项是利用；第二项是探索。根据任务调节 `c`。

### 成本现实

搜索会让 token 爆炸。ToT 在 24 点游戏上使用 100-1000 倍于 CoT 的 token。LATS 类似。这不是免费的；将搜索保留给：

- 单条轨迹明显不足的任务（24 点游戏、复杂代码）。
- 正确性比延迟更重要的任务。
- 有廉价可靠价值函数的任务（代码的单元测试、数学的明确目标）。

如果你的任务有单一正确答案和一个有噪声的评估器，搜索通常会让事情变得更糟 —— 它会找到一个"评分高"的错误答案。

### 2026 年的定位

大多数生产 Agent 不运行 LATS。它们运行带工具验证的 ReAct（CRITIC，第 5 课）。搜索出现在专业领域：

- 以测试作为价值函数的编码 Agent（HumanEval 风格）。
- 探索多条查询路径的深度研究 Agent。
- LangGraph 子图中的重度规划工作流。

AlphaEvolve（第 11 课）是 2025 年的极端案例：代码上的进化搜索、机器可检查的适应度、前沿收益（56 年来首次 4x4 矩阵乘法改进）。

## 构建它

`code/main.py` 实现了：

- 一个风格化的"选择算术运算"任务上的小型 ToT BFS。
- 同一任务上的玩具 LATS MCTS 循环（选择/展开/模拟/回传播），带 UCT 选择。
- 一个组合符号分数和自评估分数的价值函数。

运行它：

```
python3 code/main.py
```

轨迹显示 ToT 用 BFS 每个节点展开三个候选，对比 LATS 通过 MCTS 收敛到最佳模拟。两者都打印了 token 计数。

## 使用它

LangGraph 将 ToT 风格的探索作为子图模式提供；LangChain 团队关于 LATS 的博客（2024 年 5 月）是参考教程。LlamaIndex 提供了 `TreeOfThoughts` Agent。对大多数 2026 年的生产 Agent 来说，这个模式位于 `if task_complexity > threshold: use_search()` 门控之后 —— 参见第 5 课的评估器-优化器模式。

## 发布它

`outputs/skill-search-policy.md` 根据任务形态、预算和评估器保真度，在线性 ReAct、ToT、LATS 和进化搜索之间进行选择。

## 练习

1. 用 UCT c=0.1 和 c=2.0 运行玩具 LATS。轨迹有什么变化？
2. 将价值函数换成更嘈杂的评分器（添加随机抖动）。MCTS 还能找到最佳叶节点吗？它能容忍的最小信噪比是多少？
3. 实现 beam-search ToT（每层保留 top-k）并与 BFS 比较。在紧张的 token 预算下哪个更好？
4. 阅读 LATS 第 5.1 节。复现 HumanEval 轨迹计数：需要多少次模拟才能达到报告的 pass@1？
5. 阅读 LATS 论文中关于"LATS 何时帮助较小"的讨论。写一段将任务形态映射到搜索策略的决策规则。

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Tree of Thoughts | "分支 CoT" | Yao 等人 — 带自评估的思考节点树 |
| LATS | "LLM 的 MCTS" | Zhou 等人 — 在 MCTS 下统一 ToT + ReAct + Reflexion |
| UCT | "上置信界" | 平衡利用（Q）和探索（ln N / n）的选择公式 |
| Value function | "这个状态有多好" | 提示 LLM 评分或环境奖励；反馈到回传播 |
| Policy | "动作提议者" | ReAct 风格的生成器；发出候选的下一步思考/动作 |
| Rollout | "模拟轨迹" | 从节点走到叶，使用策略，用价值函数评分 |
| Backpropagate | "更新祖先" | 将叶节点的奖励沿路径向上推送，更新访问计数和 Q |
| Search cost | "Token 爆炸" | 24 点游戏上 100-1000 倍 CoT；采用前先做预算 |

## 延伸阅读

- [Yao 等人, Tree of Thoughts (arXiv:2305.10601)](https://arxiv.org/abs/2305.10601) —— 标准论文
- [Zhou 等人, LATS (arXiv:2310.04406)](https://arxiv.org/abs/2310.04406) —— 带 Reflexion 反馈的 MCTS
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) —— 搜索的子图模式
- [AlphaEvolve (arXiv:2506.13131)](https://arxiv.org/abs/2506.13131) —— 带编程评估器的进化搜索