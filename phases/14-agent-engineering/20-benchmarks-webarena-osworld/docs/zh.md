# 基准测试：WebArena 与 OSWorld

> WebArena 通过四个自托管应用测试 Web Agent 能力。OSWorld 通过 Ubuntu、Windows、macOS 测试桌面 Agent 能力。在发布时（2023-2024）两者都显示了顶级 Agent 与人类之间的巨大差距。差距在缩小；失败模式没有变。

**类型：** Learn
**语言：** Python（stdlib）
**前置课程：** Phase 14 · 19（SWE-bench, GAIA）
**时间：** ~60 分钟

## 学习目标

- 描述 WebArena 的四个自托管应用以及为什么基于执行的评估很重要。
- 解释为什么 OSWorld 使用真实 OS 截图而非无障碍 API。
- 说出 OSWorld 的两个主要失败模式：GUI 定位和操作知识。
- 总结 OSWorld-G 和 OSWorld-Human 在基础基准之上添加了什么。

## 问题

通用 Agent 可以调用工具。它们能驱动浏览器跨越 20 次点击完成购物结算吗？它们能仅用键盘和鼠标配置 Linux 机器吗？这些是 WebArena 和 OSWorld 回答的问题。

## 核心概念

### WebArena（Zhou 等人，ICLR 2024）

- 跨越四个自托管 Web 应用的 812 个长周期任务：购物网站、论坛、类 GitLab 开发工具、商业 CMS。
- 加上实用工具：地图、计算器、草稿本。
- 评估通过 gym API 基于执行 —— 订单是否已下单、issue 是否已关闭、CMS 页面是否已更新？
- 发布时：最佳 GPT-4 Agent 达到 14.41% 成功率 vs 人类 78.24%。

自托管的框架很重要 —— 基准不脆弱，因为目标应用是固定的且可复现的。

### 扩展

- **VisualWebArena** — 视觉定位任务，成功取决于解释图像（截图作为一等观察）。
- **TheAgentCompany**（2024 年 12 月）—— 添加终端 + 编码；更像真实的远程工作环境。

### OSWorld（Xie 等人，NeurIPS 2024）

- 跨越 Ubuntu、Windows、macOS 的 369 个真实计算机任务。
- 对真实应用的自由键盘和鼠标控制。
- 1920×1080 截图作为观察。
- 发布时：最佳模型 12.24% vs 人类 72.36%。

### 主要失败模式

1. **GUI 定位。** 像素 → 元素映射。模型难以在 1920×1080 中可靠地定位 UI 元素。
2. **操作知识。** 哪个菜单有设置、哪个键盘快捷键、哪个偏好面板。人类多年积累的知识长尾。

### 后续

- **OSWorld-G** — 564 样本定位套件 + Jedi 训练集。将定位从规划中分解，以便你可以单独衡量它们。
- **OSWorld-Human** — 人工策划的黄金动作轨迹。显示顶级 Agent 使用比必要多 1.4-2.7 倍的步骤（轨迹效率差距）。

### 为什么这很重要

Claude computer use、OpenAI CUA、Gemini 2.5 Computer Use（第 21 课）都在由 WebArena 和 OSWorld 塑形的工作负载上训练。基准是目标；生产模型是发布的答案。

### 基准测试出错的地方

- **仅截图评估。** OSWorld 是截图驱动的；在 OSWorld 上评估使用 DOM 或无障碍 API 的 Agent 会遗漏定位挑战。
- **忽略轨迹长度。** 仅评分成功率会遗漏 OSWorld-Human 呈现的 1.4-2.7 倍步骤低效。
- **过时的自托管应用。** WebArena 的应用固定特定版本；更新而不重新策划会破坏可比性。

## 构建它

`code/main.py` 实现了一个玩具 Web Agent 框架：

- 一个最小的"购物应用"状态机：list_items、add_to_cart、checkout。
- 3 个任务的黄金轨迹。
- 尝试每个任务的脚本化 Agent。
- 基于执行的评估器（状态检查）和轨迹效率指标（步骤 vs 黄金）。

运行它：

```
python3 code/main.py
```

输出：每任务成功率和轨迹效率，镜像 OSWorld-Human 的方法论。

## 使用它

- **WebArena Verified** 在内部集群上自托管进行持续评估。
- **OSWorld** 在 VM 集群中用于桌面 Agent。
- **计算机使用 Agent**（第 21 课）—— Claude、OpenAI CUA、Gemini —— 都在类似的工作负载上训练。
- **你自己的产品流程** —— 为你前 20 个任务捕获黄金轨迹；每周用 Agent 运行它们。

## 发布它

`outputs/skill-web-desktop-harness.md` 构建一个 Web/桌面 Agent 框架，带基于执行的评估和轨迹效率指标。

## 练习

1. 用第二个应用（论坛）扩展玩具框架。编写 3 个任务加黄金轨迹。
2. 添加每任务轨迹效率报告。在你的玩具上，Agent 是黄金的 1x、2x 还是 3x？
3. 实现一个"干扰"工具 —— 黄金轨迹从不使用的工具。脚本化 Agent 会被诱惑吗？
4. 阅读 OSWorld-G。你如何在自己的评估中分离定位失败和规划失败？
5. 阅读 WebArena 的应用 README。当你升级一个固定版本时什么会出问题？

## 关键术语

| 术语 | 人们怎么说 | 实际含义 |
|------|-----------|---------|
| WebArena | "Web Agent 基准" | 跨 4 个自托管应用的 812 个任务；gym 风格评估 |
| VisualWebArena | "视觉 WebArena" | 视觉定位的 WebArena；截图是观察 |
| OSWorld | "桌面 Agent 基准" | 真实 Ubuntu/Windows/macOS 上的 369 个任务 |
| GUI grounding | "像素到元素映射" | 模型在 1920x1080 中定位 UI 元素 |
| Operational knowledge | "OS 操作知识" | 哪个菜单、哪个快捷键、哪个偏好面板 |
| OSWorld-G | "定位套件" | 564 个纯定位样本 + 训练集 |
| OSWorld-Human | "黄金轨迹" | 用于衡量效率的人工专家动作序列 |
| Trajectory efficiency | "步骤超过黄金" | Agent 步骤数除以人类最小步骤数 |

## 延伸阅读

- [Zhou 等人, WebArena (arXiv:2307.13854)](https://arxiv.org/abs/2307.13854) — 四应用 Web 基准
- [Xie 等人, OSWorld (arXiv:2404.07972)](https://arxiv.org/abs/2404.07972) — 跨 OS 桌面基准
- [Anthropic, Introducing computer use](https://www.anthropic.com/news/3-5-models-and-computer-use) — Claude 的基准形态能力
- [OpenAI, Computer-Using Agent](https://openai.com/index/computer-using-agent/) — OSWorld 和 WebArena 数字