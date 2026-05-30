# Janus-Pro：统一多模态模型的解耦编码器

> 统一多模态模型存在一个不可避免的张力。理解需要语义特征——SigLIP 或 DINOv2 输出富含概念级信息的向量。生成需要重建友好的编码——能组合回清晰像素的 VQ token。两个目标在单一编码器中不兼容。Janus（DeepSeek，2024 年 10 月）和 Janus-Pro（DeepSeek，2025 年 1 月）认为修复方法是停止尝试：解耦两个编码器。在任务之间共享 Transformer 主体，但理解通过 SigLIP 路由，生成通过 VQ tokenizer 路由。在 70 亿参数下，Janus-Pro 在 GenEval 上击败 DALL-E 3 同时在 MMMU 上匹配 LLaVA。本课解读为什么两个编码器在一个编码器失败的地方有效。

**类型：** Build
**语言：** Python（标准库，双编码器路由 + 共享主体信号）
**前置课程：** Phase 12 · 13（Transfusion）、Phase 12 · 14（Show-o）
**时间：** ~120 分钟

## 学习目标

- 解释为什么单一共享编码器会在理解或生成质量上做出妥协。
- 描述 Janus-Pro 的路由：理解时输入端使用 SigLIP 特征，生成时输入和输出都使用 VQ token。
- 追踪使 Janus-Pro 在 Janus 失败之处成功的数据混合缩放。
- 对比解耦（Janus-Pro）、耦合连续（Transfusion）和耦合离散（Show-o）架构。

## 问题

统一模型在理解和生成之间共享 Transformer 主体。之前的尝试（Chameleon、Show-o、Transfusion）都为两个方向使用同一个视觉 tokenizer。tokenizer 是一个折中：

- 为重建优化（生成）：VQ-VAE 捕获细粒度像素细节但产生语义连贯性弱的 token。
- 为语义优化（理解）：SigLIP 嵌入将"猫"图像聚集在"猫"token 附近但不允许好的重建。

Show-o 和 Transfusion 在一个方向上付出了可见的质量代价。Janus-Pro 提问：当任务有不同需求时，为什么要求一个 tokenizer？

## 概念

### 解耦视觉编码

Janus-Pro 的架构分离了两个编码器：

- **理解路径**。输入图像 → SigLIP-SO400m → 2 层 MLP → Transformer 主体。
- **生成路径**。输入图像（如果以现有图像为条件）→ VQ tokenizer → token ID → Transformer 主体。
- **输出生成**。Transformer 预测的图像 token → VQ 解码器 → 像素。

Transformer 主体是共享的。主体上游和下游的所有内容都是任务特定的。

输入通过提示格式消歧：`<understand>` 标签通过 SigLIP 路由；`<generate>` 通过 VQ 路由。或者路由从任务中隐式确定。

### 为什么有效

理解损失获得 SigLIP 特征，CLIP 风格预训练已将其调优为语义相似性。模型的感知基准相比 Show-o / Transfusion 有所提升，因为输入特征更适合该任务。

生成损失获得 VQ token，tokenizer 已将其调优为重建。图像质量相比 Show-o 有所提升，因为 VQ 编码能干净地组合回像素。

共享 Transformer 主体看到两种输入分布（SigLIP 和 VQ）并学习处理两者。声明：足够的数据 + 足够的参数，主体吸收了切换。

### 数据缩放——Janus vs Janus-Pro

Janus（原始版，arXiv 2410.13848）引入了解耦但规模较小（13 亿参数，有限数据）。Janus-Pro（arXiv 2501.17811）扩展了：

- 70 亿参数（vs 13 亿）。
- 阶段 1（对齐）9000 万图文对，从 7200 万增加。
- 阶段 2（统一）7200 万，从 2600 万增加。
- 阶段 3 增加了 20 万图像生成指令样本。

结果：Janus-Pro-7B 在 MMMU 上匹配 LLaVA（60.3 vs ~58），在 GenEval 上击败 DALL-E 3（0.80 vs 0.67）。一个开源模型，在统一光谱的两侧都具有竞争力。

### JanusFlow——整流流变体

JanusFlow（arXiv 2411.07975）将 VQ 生成路径换成整流流生成路径（连续）。拆分变为 SigLIP 用于理解 + 整流流用于生成。质量天花板进一步提升。架构保持解耦编码器-共享主体。

### 共享主体的职责

Transformer 主体处理统一序列但有两种输入分布。其职责是：

- 理解时：消费 SigLIP 特征 + 文本 token → 自回归发出文本。
- 生成时：消费文本 token +（可选图像 VQ token）→ 自回归发出图像 VQ token。

主体没有每块模态特定的权重。它是你在 Qwen 或 Llama 中能找到的文本风格 Transformer，加上两个输入适配器。

有趣的是，这意味着 Janus-Pro 的主体可以从预训练 LLM 初始化。Janus-Pro 确实从 DeepSeek-MoE-7B 初始化。这个选择很重要：LLM 贡献了纯从头统一模型难以达到的推理能力。

### 与 InternVL-U 的对比

InternVL-U（课程 12.10）是 2026 年的后续。它结合了：

- 原生多模态预训练（InternVL3 骨干网络）。
- 解耦编码器路由（SigLIP 输入，VQ + 扩散头输出）。
- 统一理解 + 生成 + 编辑。

InternVL-U 将 Janus-Pro 的架构选择纳入更大的框架。解耦编码器思想现在是大规模统一模型的默认选择。

### 局限性

解耦编码器增加了架构复杂度。两个 tokenizer 要训练，两条输入路径要维护，两组失败模式。对于不需要生成的产品，Janus-Pro 是过度设计的——选择 LLaVA 系列理解模型。

对于不需要理解的产品，Janus-Pro 是大材小用——选择 Stable Diffusion 3 / Flux 模型。

对于两者都需要的产品，Janus-Pro 现在是参考开源架构。

## 使用它

`code/main.py` 模拟 Janus-Pro 路由：

- 两个模拟编码器：类 SigLIP（产生 256 维语义向量）和类 VQ（产生整数码）。
- 根据任务标签选择编码器的提示路由器。
- 共享主体（替代品）处理 token 序列，无论哪个编码器产生了它们。
- 从阶段 1（对齐）到阶段 3（指令微调）的加权样本调度切换。

打印 3 个示例的路由路径：图像 QA、T2I、图像编辑。

## 产出

本课生成 `outputs/skill-decoupled-encoder-picker.md`。给定一个想要统一生成 + 理解且质量接近前沿的产品，在 Janus-Pro、JanusFlow 或 InternVL-U 之间做出具体数据规模推荐的选择。

## 练习

1. Janus-Pro-7B 在 GenEval 上击败 DALL-E 3。解释为什么 70 亿开源模型能在生成上匹配前沿专有模型但在理解上不能。

2. 实现一个路由器函数：给定提示文本，分类为 `understand` 或 `generate`。你如何处理"描述然后画草图"这样模糊的提示？

3. JanusFlow 用整流流替换了 VQ 路径。Transformer 主体现在输出什么，损失有什么变化？

4. 提出 Janus-Pro 架构可以用再多一个解耦编码器处理的第四个任务。示例：图像分割（DINO 风格）、深度（MiDaS 风格）。

5. 阅读 Janus-Pro 第 4.2 节关于数据缩放。哪个数据阶段对 T2I 质量提升相比 Janus 贡献最大？

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Decoupled encoding（解耦编码） | "两个视觉编码器" | 每个方向使用独立的 tokenizer 或编码器：语义用于理解，重建用于生成 |
| Shared body（共享主体） | "一个 Transformer" | 单一 Transformer 处理任一编码器的输出；无模态特定权重 |
| SigLIP for understanding | "语义特征" | CLIP 系列视觉塔提供丰富概念特征但重建能力差 |
| VQ for generation | "重建编码" | 能干净地解码回像素的向量量化 token |
| JanusFlow | "整流流变体" | 用连续流匹配生成头替代 VQ 的 Janus-Pro |
| Routing tag（路由标签） | "任务标签" | 选择输入编码器的提示标记（`<understand>` / `<generate>`） |

## 延伸阅读

- [Wu 等人 — Janus (arXiv:2410.13848)](https://arxiv.org/abs/2410.13848)
- [Chen 等人 — Janus-Pro (arXiv:2501.17811)](https://arxiv.org/abs/2501.17811)
- [Ma 等人 — JanusFlow (arXiv:2411.07975)](https://arxiv.org/abs/2411.07975)
- [InternVL-U (arXiv:2603.09877)](https://arxiv.org/abs/2603.09877)
- [Dong 等人 — DreamLLM (arXiv:2309.11499)](https://arxiv.org/abs/2309.11499)