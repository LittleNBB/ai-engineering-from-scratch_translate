# 技能库与终身学习（Voyager）

> Voyager（Wang 等人，TMLR 2024）将可执行代码视为技能。技能是命名的、可检索的、可组合的，并通过环境反馈进行优化。这是 Claude Agent SDK 技能、skillkit 和 2026 年技能库模式的参考架构。

**类型：** Build
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 07（MemGPT）、Phase 14 · 08（Letta Blocks）
**时间：** ~75 分钟

## 学习目标

- 说出 Voyager 的三个组件 —— 自动课程、技能库、迭代提示 —— 及其各自的角色。
- 解释为什么 Voyager 将动作空间设为代码而非原始命令。
- 用标准库实现一个带注册、检索、组合和失败驱动优化的技能库。
- 将 Voyager 的模式映射到 2026 年 Claude Agent SDK 技能和 skillkit 生态系统。

## 问题

在每次会话中从零重建所有能力的 Agent 做错了三件事：

1. **浪费 token。** 每个任务都重新引出相同的推理。
2. **丢失进度。** 在会话 A 中学到的修正不会转移到会话 B。
3. **在长周期组合上失败。** 复杂任务需要能力层级；一次性提示无法表达它们。

Voyager 的答案：将每个可复用能力视为一个命名的代码块，存储在库中，可通过相似度检索，可与其他技能组合，并通过执行反馈进行优化。

## 核心概念

### 三个组件

Voyager（arXiv:2305.16291）围绕以下结构构建 Agent：

1. **自动课程。** 一个好奇心驱动的提议器根据 Agent 当前的技能集和环境状态选择下一个任务。探索是自下而上的。
2. **技能库。** 每个技能是可执行代码。任务成功时添加新技能。通过查询与描述的相似度检索技能。
3. **迭代提示机制。** 失败时，Agent 接收执行错误、环境反馈和自验证输出，然后优化技能。

Minecraft 评估（Wang 等人，2024）：独特物品多 3.3 倍、石器快 8.5 倍、铁器快 6.4 倍、地图遍历长 2.3 倍，相比基线。数字是 Minecraft 特有的，但模式可转移。

### 动作空间 = 代码

大多数 Agent 发出原始命令。Voyager 发出 JavaScript 函数。一个技能是：

```
async function craftIronPickaxe(bot) {
  await mineIron(bot, 3);
  await mineStick(bot, 2);
  await placeCraftingTable(bot);
  await craft(bot, 'iron_pickaxe');
}
```

由子技能组合而成。以描述和 embedding 为键存储。作为程序而非提示检索。

这就是 2026 年 Claude Agent SDK 的技能：一个命名的、可检索的代码块加上 Agent 按需加载的指令。

### 技能检索

新任务"制作钻石镐"。Agent：

1. 嵌入任务描述。
2. 查询技能库获取 top-k 相似技能。
3. 检索 `craftIronPickaxe`、`mineDiamond`、`placeCraftingTable` 等。
4. 从检索到的原始技能 + 新逻辑组合新技能。

这是 MCP 资源（Phase 13）和 Agent SDK 技能实现的模式：在知识/代码表面上检索，范围限定到当前任务。

### 迭代优化

Voyager 的反馈循环：

1. Agent 编写一个技能。
2. 技能对环境运行。
3. 返回三种信号之一：`success`、`error`（带堆栈跟踪）、`self-verification failure`。
4. Agent 使用信号作为上下文重写技能。
5. 循环直到成功或达到最大轮数。

这是 Self-Refine（第 5 课）应用于带有环境验证的代码生成。CRITIC（第 5 课）是使用外部工具作为验证器的同一模式。

### 课程与探索

Voyager 的课程模块根据 Agent 已有的和尚未做过的事情提出任务，如"在湖边建造一个庇护所"。提议器使用环境状态 + 技能清单来选择刚好超出当前能力的任务 —— 探索的甜蜜点。

对于生产 Agent，这转化为一个"缺失什么"的算子：给定当前技能库和一个领域，我们还没有覆盖哪些技能？团队通常以课程审查的形式手动实现这一点。

### 这个模式出错的地方

- **技能库腐烂。** 同一个技能被添加了 10 次，描述略有不同。在写入时添加去重；检索只返回一个。
- **组合技能漂移。** 父技能依赖一个已被优化的子技能。给技能版本化；固定在 v1 的父技能不会神奇地拾取 v3。
- **检索质量。** 当库增长到几百个以上时，基于技能描述的向量检索会退化。用标签过滤器和硬约束（"仅 `category=tooling` 的技能"）补充。

## 构建它

`code/main.py` 用标准库实现了一个技能库：

- `Skill` — 名称、描述、代码（作为字符串）、版本、标签、依赖。
- `SkillLibrary` — 注册、搜索（token 重叠）、组合（依赖拓扑排序）和优化（更新时版本升级）。
- 一个脚本化 Agent，注册三个原始技能，组合第四个，遇到失败，然后优化。

运行它：

```
python3 code/main.py
```

轨迹展示了库写入、检索、组合、一次失败执行和 v2 优化 —— Voyager 循环的端到端。

## 使用它

- **Claude Agent SDK 技能**（Anthropic）—— 2026 年的参考：每个技能有描述、代码和指令；在 Agent 会话中按需加载。
- **skillkit**（npm: skillkit）—— 面向 32+ AI 编码 Agent 的跨 Agent 技能管理。
- **自定义技能库** —— 领域特定（数据 Agent 的 SQL 技能、基础设施 Agent 的 Terraform 技能）。Voyager 模式可以缩小规模。
- **OpenAI Agents SDK `tools`** —— 低端；每个工具是一个轻量级技能。

## 发布它

`outputs/skill-skill-library.md` 为任何目标运行时生成一个 Voyager 形态的技能库，带注册、检索、版本控制和优化。

## 练习

1. 给 `compose()` 添加依赖循环检测器。当技能 A 依赖 B 而 B 依赖 A 时会发生什么？错误还是警告？
2. 实现每技能版本锁定。当父技能组合子技能 `crafting@1` 时，对 `crafting@2` 的优化不应静默升级父技能。
3. 用 sentence-transformers embeddings（或 BM25 标准库实现）替换 token 重叠检索。在 50 个技能的玩具库上衡量 retrieval@5。
4. 添加一个"课程"Agent：给定当前库和领域描述，提议 5 个缺失的技能。每周调用。
5. 阅读 Anthropic 的 Claude Agent SDK 技能文档。将玩具库移植到 SDK 的技能 schema。可发现性有什么变化？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| Skill | "可复用能力" | 命名的代码块 + 描述，可通过相似度检索 |
| Skill library | "Agent 的操作记忆" | 技能的持久存储，可搜索和组合 |
| Curriculum | "任务提议器" | 由当前能力差距驱动的自下而上目标生成器 |
| Composition | "技能 DAG" | 技能调用技能；执行时拓扑排序 |
| Iterative refinement | "自纠正循环" | 环境反馈 + 错误 + 自验证折叠回下一个版本 |
| Action-space-as-code | "程序化动作" | 发出函数而非原始命令，用于时间扩展行为 |
| Dedup on write | "技能折叠" | 近似重复描述折叠为一个标准技能 |

## 延伸阅读

- [Wang 等人, Voyager (arXiv:2305.16291)](https://arxiv.org/abs/2305.16291) — 原始技能库论文
- [Claude Agent SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview) — 技能作为 2026 年的产品化
- [Anthropic, Building agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk) — 实践中的技能和子 Agent
- [Madaan 等人, Self-Refine (arXiv:2303.17651)](https://arxiv.org/abs/2303.17651) — Voyager 底层的优化循环