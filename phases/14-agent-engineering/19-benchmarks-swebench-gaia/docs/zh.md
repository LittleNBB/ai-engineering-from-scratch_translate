# 基准测试：SWE-bench、GAIA、AgentBench

> 三个基准测试在 2026 年锚定了 Agent 评估。SWE-bench 测试代码补丁。GAIA 测试通用工具使用。AgentBench 测试多环境推理。了解它们的组成、污染故事以及它们不衡量什么。

**类型：** Learn
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 06（Tool Use）
**时间：** ~60 分钟

## 学习目标

- 说出 SWE-bench 的测试框架（FAIL_TO_PASS）并解释为什么它以单元测试为门控。
- 解释为什么 SWE-bench Verified（OpenAI，500 个任务）存在以及它移除了什么。
- 描述 GAIA 的设计：对人类简单，对 AI 困难；三个难度级别。
- 说出 AgentBench 的八个环境及其对开源 LLM 的主要阻碍。
- 总结 SWE-bench+ 污染发现及其影响。

## 问题

排行榜告诉你哪个模型在某个基准上获胜。它们不告诉你：

- 基准是否被污染（训练数据中的解决方案、测试泄露）。
- 基准是否衡量你关心的东西（代码 vs 浏览 vs 通用）。
- 评估器是否健壮（AST 匹配、状态检查、人工审查）。

在引用数字之前，先了解三个锚定基准及其失败模式。

## 核心概念

### SWE-bench（Jimenez 等人，ICLR 2024 oral）

- 来自 12 个流行 Python 仓库的 2,294 个真实 GitHub issue。
- Agent 获得：修复前提交的代码库 + 自然语言 issue 描述。
- Agent 产出：一个补丁。
- 评估器：应用补丁，运行仓库的测试套件。补丁必须翻转 FAIL_TO_PASS 测试（之前失败，现在通过）而不破坏 PASS_TO_PASS 测试。

SWE-agent（Yang 等人，2024）在发布时通过强调 Agent-计算机接口（文件编辑器命令、模型理解的搜索语法）达到了 12.5%。

### SWE-bench Verified

OpenAI，2024 年 8 月。人工策划的 500 个任务子集。移除了模糊的 issue、不可靠的测试和修复不明确的任务。"你的 Agent 是否发布真实补丁？"的主要基准。

### 污染

- 超过 94% 的 SWE-bench issue 早于大多数模型的截止日期。
- **SWE-bench+** 发现 32.67% 的成功补丁在 issue 文本中泄露了解决方案（模型在描述中看到了修复），31.08% 由于弱测试覆盖而可疑。
- Verified 更干净但并非无污染。

实际影响：在 SWE-bench 上得分 50% 的模型可能在 SWE-bench+ 上得分 35%。如果你声称 SWE-bench 性能，始终同时报告两者。

### GAIA（Mialon 等人，2023 年 11 月）

- 466 个问题；300 个保留用于 huggingface.co/gaia-benchmark 的私有排行榜。
- 设计哲学："概念上对人类简单（92%）但对 AI 困难（GPT-4 带插件：15%）。"
- 测试推理、多模态、Web、工具使用。
- 三个难度级别；级别 3 需要跨模态的长工具链。

GAIA 是你用来衡量"通用能力"的。不要与代码特定基准混淆。

### AgentBench（Liu 等人，ICLR 2024）

- 8 个环境，跨越代码（Bash、DB、KG）、游戏（Alfworld、LTP）、Web（WebShop、Mind2Web）和开放式生成。
- 多轮，每个分割约 4k-13k 轮。
- 主要发现：长期推理、决策和指令跟随是开源 LLM 追赶商业模型的阻碍。

### 这些不衡量什么

- 真实世界的运营成本（token、挂钟时间）。
- 对抗条件下的安全行为。
- 你领域上的性能（使用你自己的评估，第 30 课）。
- 尾部故障（基准取平均；生产运维人员关心最差的 1%）。

### 基准测试出错的地方

- **单一数字执着。** SWE-bench 50% 告诉你的比 P50/P75/P95 成本 + 步骤分布少。
- **污染声明。** 报告 SWE-bench 而不提及 Verified 或 SWE-bench+ 是误导性的。
- **基准即开发目标。** 为基准优化会偏离生产有用性。

## 构建它

`code/main.py` 实现了一个玩具 SWE-bench 类框架：

- 合成 bug 修复任务（3 个任务）。
- 一个脚本化的"Agent"提出补丁。
- 一个测试运行器检查 FAIL_TO_PASS（bug 已修复）和 PASS_TO_PASS（没有破坏）。
- 基于问题分解深度的 GAIA 风格难度分类器。

运行它：

```
python3 code/main.py
```

输出展示了每个任务和每个难度的解决率，使评估器规则具体化。

## 使用它

- **SWE-bench Verified** 用于代码 Agent。始终报告 Verified 分数。
- **GAIA** 用于通用 Agent。使用私有排行榜分割。
- **AgentBench** 用于多环境比较。
- **自定义评估**（第 30 课）用于你产品的实际形状。

## 发布它

`outputs/skill-benchmark-harness.md` 为任何代码库-任务对构建 SWE-bench 风格的框架，带 FAIL_TO_PASS / PASS_TO_PASS 门控。

## 练习

1. 将玩具框架移植到在真实仓库上运行（选一个你的）。为已知 bug 编写 3 个 FAIL_TO_PASS 测试。
2. 添加步数指标。在你的 3 个任务上，每个解决需要多少 Agent 步骤？
3. 阅读 SWE-bench+ 论文。实现解决方案泄露检查（模式匹配 issue 文本与 diff）。
4. 从公共分割下载一个 GAIA 问题。追踪一个 GPT-4 级别 Agent 会做什么。它需要什么工具？
5. 阅读 AgentBench 的每环境分解。哪个环境镜像你的产品场景？"SOTA"在那里是什么样的？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| SWE-bench | "代码 Agent 基准" | 2,294 个 GitHub issue；补丁必须翻转 FAIL_TO_PASS 测试 |
| SWE-bench Verified | "干净的 SWE-bench" | 500 个人工策划的任务，OpenAI |
| FAIL_TO_PASS | "修复门控" | 之前失败的测试在补丁后必须通过 |
| PASS_TO_PASS | "无回归门控" | 之前通过的测试必须仍然通过 |
| GAIA | "通用基准" | 466 个对人类简单/对 AI 困难的多工具问题 |
| AgentBench | "多环境基准" | 8 个环境；长周期多轮 |
| Contamination | "训练集泄露" | 基准任务出现在模型训练中 |
| SWE-bench+ | "污染审计" | 在成功 SWE-bench 补丁中发现 32.67% 的解决方案泄露 |

## 延伸阅读

- [Jimenez 等人, SWE-bench (arXiv:2310.06770)](https://arxiv.org/abs/2310.06770) — 原始基准
- [OpenAI, SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) — 策划子集
- [Mialon 等人, GAIA (arXiv:2311.12983)](https://arxiv.org/abs/2311.12983) — 通用基准
- [Liu 等人, AgentBench (arXiv:2308.03688)](https://arxiv.org/abs/2308.03688) — 多环境套件