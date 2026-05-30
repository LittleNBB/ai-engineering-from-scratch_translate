# Flamingo 与门控交叉注意力实现少样本 VLM

> DeepMind 的 Flamingo（2022）率先做了两件事。它展示了一个模型可以处理任意交错的图像、视频和文本序列。它还展示了 VLM 可以进行上下文学习——给出包含三个示例（图像，描述）对的少样本提示，模型就能为新图像生成描述，无需任何梯度更新。机制是：门控交叉注意力层，插入冻结 LLM 的现有层之间，带有学习的 tanh 门控，初始化为零，因此 LLM 的文本能力在初始化时得以保留。本课走读 Flamingo 的 Perceiver resampler 和门控交叉注意力架构——Gemini 交错输入和 Idefics2 视觉 token 的祖先。

**类型：** Learn
**语言：** Python（标准库，门控交叉注意力 + Perceiver resampler 演示）
**前置课程：** Phase 12 · 03（BLIP-2 Q-Former）
**时间：** ~120 分钟

## 学习目标

- 解释门控交叉注意力如何通过 tanh(gate) = 0 在初始化时保留冻结 LLM 的文本能力。
- 走读 Perceiver resampler：N 个图像 patch → K 个固定的"潜在"query 通过交叉注意力。
- 描述 Flamingo 如何处理交错的图像-文本序列，使用尊重图像位置的因果掩码。
- 复现一个少样本多模态提示结构（3 个图像-描述示例然后一个查询图像）。

## 问题

BLIP-2 将 32 个视觉 token 输入冻结 LLM 的输入层。对每个提示一张图像有效。但如果你想将*多张*图像与文本交错输入，比如"这是图像 A，描述它；这是图像 B，描述它；现在这是图像 C，描述它"呢？LLM 的自注意力需要在单个流中处理图像 token 和文本 token，而哪些位置可以关注哪些图像的问题变得复杂。

Flamingo 的回答：完全不改变 LLM 的输入流。在现有 LLM 层之间插入额外的交叉注意力层。文本 token 仍然像往常一样通过 LLM 的因果自注意力。每隔几层 LLM 层，文本 token 也通过一个新的门控层交叉关注图像特征。门控（初始化为零）意味着在第一步时新层是无操作的——模型表现得完全像预训练的 LLM。随着训练的推进，门控打开，视觉信息开始流动。

Flamingo 回答的第二个问题：如何处理每个提示可变数量的图像（0、1 或多张）？Perceiver resampler——一个小型交叉注意力模块，接收任意数量的 patch 并产生固定数量的视觉潜在 token。无论提示中有多少图像，LLM 的交叉注意力层看到的形状都相同。

## 概念

### 冻结的 LLM

Flamingo 从一个冻结的 Chinchilla 70B LLM 开始。所有 70B 权重不动。现有的文本自注意力和 FFN 正常运行。

### Perceiver resampler

对于提示中的每张图像，ViT 产生 N 个 patch token。Perceiver resampler 有 K 个固定的可学习潜在向量（Flamingo 使用 K=64）。每个 resampler 块有两个子步骤：

1. 交叉注意力：K 个潜在向量关注 N 个 patch token（Q 来自潜在向量，K/V 来自 patch）。
2. 潜在向量之间的自注意力 + FFN。

经过 6 个 resampler 块后，输出是 K=64 个维度为 1024 的视觉 token，无论 ViT 产生了多少 patch。224×224 的图像（196 个 patch）和 480×480 的图像（900 个 patch）都输出 64 个 resampler token。

对于视频，resampler 在时间维度上应用：每帧的 patch 产生 64 个潜在向量，时间位置编码让模型区分 t=0 和 t=N。完整的视频成为 T × 64 个视觉 token。

### 门控交叉注意力

在冻结 LLM 的每 M 层之间（Flamingo 使用 M=4），插入一个新的门控交叉注意力块：

```
x_after_llm_block = llm_block(x_before)
cross = cross_attn(x_after, resampler_output)
gated = tanh(alpha) * cross + x_after
x_before_next_block = gated
```

- `alpha` 是一个可学习的标量，初始化为零。
- `tanh(0) = 0`，因此在初始化时门控分支贡献为零。
- 当 `alpha` 偏离零时，交叉注意力的贡献平滑增长。
- 残差连接意味着即使门完全打开也不会覆盖 LLM 的文本表示；它只是在上面添加视觉信息。

这是 Flamingo 中最重要的设计选择：视觉条件化是加性的、门控的、初始化为零的。步骤 0 的 Flamingo 在纯文本输入上是完美的 Chinchilla 70B。

### 交错输入的掩码交叉注意力

在像"<image A> caption A <image B> caption B <image C> ?"这样的提示中，每个文本 token 只应该看到序列中在它之前的图像。交叉注意力掩码强制执行：位置 `t` 的文本 token 只关注图像索引 `i < i_t` 的图像 resampler token，其中 `i_t` 是位置 `t` 之前最近的图像。"只看到前一张图像"或"看到所有前面的图像"都是有效的选择；Flamingo 选择了前者。

### 上下文少样本学习

Flamingo 提示看起来像：

```
<image1> A photo of a cat. <image2> A photo of a dog. <image3> A photo of a
```

模型看到补全模式并输出"bird"（或 image3 显示的任何内容）。没有梯度更新。冻结 LLM 的上下文学习能力通过门控交叉注意力延续——这是论文的核心要点，也是其重要性的原因。

### 训练数据

Flamingo 在三个数据集上训练：

1. MultiModal MassiveWeb（M3W）：4300 万个带有交错图像和文本的网页，重建阅读顺序。
2. 图文对（ALIGN + LTIP）：44 亿对。
3. 视频文本对（VTP）：2700 个短视频片段。

OBELICS（2023）是交错网络语料库的开源复现，Idefics、Idefics2 和大多数开源"类 Flamingo"模型在其上训练。

### OpenFlamingo 和 Otter

OpenFlamingo（2023）是开源复现。架构完全相同（Perceiver resampler + 在冻结 LLaMA 或 MPT 上的门控交叉注意力）。3B、4B、9B 的 checkpoint。由于基础 LLM 更小、数据更少，质量落后于 Flamingo。

Otter（2023）基于 OpenFlamingo，在 MIMIC-IT（多模态指令数据集）上进行指令微调，表明门控交叉注意力也适用于指令遵循。

### 后裔

- Idefics / Idefics2 / Idefics3：Hugging Face 的门控交叉注意力系列，逐步简化（Idefics2 放弃了 resampler，转而使用带自适应池化的直接 patch token）。
- Flamingo 到 Chameleon 的过渡：到 2024 年，许多团队转向早期融合（课程 12.11）；Flamingo 风格的门控交叉注意力在需要冻结骨干网络的场景中仍在生产中使用。
- Gemini 的交错输入：概念上继承了 Flamingo 的交错格式灵活性，但具体机制是专有的。

### 与 BLIP-2 的对比

| | BLIP-2 | Flamingo |
|---|---|---|
| 视觉桥接 | Q-Former 仅在输入层一次 | 每 M 层门控交叉注意力 |
| 视觉 token | 每张图像 32 个 | 每张图像每交叉注意力层 64 个 |
| 冻结 LLM | 是 | 是 |
| 少样本上下文 | 弱 | 强——论文的核心 |
| 交错输入 | 无原生支持 | 是，设计目标 |
| 训练数据 | 1.3 亿对 | 13 亿对 + 4300 万交错页面 |
| 参数量 | 1.88 亿训练 | 约 100 亿训练（交叉注意力层） |
| 计算 | 8 张 A100 数天 | 数千 TPUv4 数周 |

选择 BLIP-2 用于预算内的单图像 VQA。选择 Flamingo/Idefics2 用于交错、少样本或多图像推理。

## 使用它

`code/main.py` 演示了：

1. 对 36 个假 patch token 使用 8 个可学习潜在向量的 Perceiver resampler（纯 Python 交叉注意力）。
2. 门控交叉注意力步骤：`alpha = 0` → 输出等于输入（LLM 不变），然后 `alpha = 2.0` → 视觉贡献混合进来。
3. 交错掩码构建器，为"(image 1) (text 1) (image 2) (text 2)"序列生成二维注意力掩码。

## 产出

本课生成 `outputs/skill-gated-bridge-diagnostic.md`。给定一个开源 VLM 的配置（resampler 有/无、交叉注意力频率、门控方案），它识别 Flamingo 谱系元素并解释冻结策略。用于调试为什么微调降低了文本性能（答案：门控开得太快太宽）。

## 练习

1. 计算 Flamingo-9B 的视觉参数量：9B LLM + 14 亿门控交叉注意力层 + 6400 万 resampler。训练参数占总参数的比例是多少？

2. 在 PyTorch 中实现门控残差 `y = tanh(alpha) * cross + x`。实验性地展示在 `alpha=0` 时，初始化时 `y==x` 精确成立。

3. 阅读 OpenFlamingo 第 3.2 节（arXiv:2308.01390），了解他们如何在每个提示有不同图像数量时处理 batch 中的多张图像。描述填充策略。

4. 为什么 Flamingo 的交叉注意力掩码让文本 token 只关注*最近的*前一张图像而非所有前面的图像？阅读 Flamingo 论文第 2.4 节并解释权衡。

5. 上下文少样本学习：为一个新的 Flamingo 变体构建一个包含 4 个"图像 → 主要物体颜色"示例的提示。描述当你将示例数量从 0 变化到 8 时的预期准确率模式。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Perceiver resampler | "固定潜在交叉注意力" | 从可变数量的输入 patch 产生 K 个固定 token 的模块 |
| Gated cross-attention（门控交叉注意力） | "Tanh 门控桥接" | 残差层 `y = tanh(alpha)*cross + x`，可学习 alpha，初始化为 0 |
| Interleaved input（交错输入） | "混合序列" | 图像和文本按阅读顺序自由混合的提示格式 |
| Frozen LLM（冻结 LLM） | "无 LLM 梯度" | 文本 LLM 的权重不更新；仅 resampler + 交叉注意力层训练 |
| Few-shot（少样本） | "上下文示例" | 在提示中给出少量（图像，答案）对；模型无需微调即可泛化 |
| OBELICS | "交错网络语料库" | 1.41 亿个带有按阅读顺序排列的图像和文本的网页的开源数据集 |
| Chinchilla | "70B 冻结基础" | Flamingo 的冻结文本 LLM，来自 DeepMind 的 Chinchilla 论文 |
| Gate schedule（门控调度） | "alpha 如何移动" | 训练期间交叉注意力门控打开的速率 |
| Cross-attn frequency（交叉注意力频率） | "每 M 层" | 门控交叉注意力块插入的频率；Flamingo 使用 M=4 |
| OpenFlamingo | "开源复现" | MosaicML/LAION 的 3-9B 开源 checkpoint；架构与 Flamingo 完全相同 |

## 延伸阅读

- [Alayrac 等人 — Flamingo (arXiv:2204.14198)](https://arxiv.org/abs/2204.14198) — 原始论文。
- [Awadalla 等人 — OpenFlamingo (arXiv:2308.01390)](https://arxiv.org/abs/2308.01390) — 开源复现。
- [Laurençon 等人 — OBELICS (arXiv:2306.16527)](https://arxiv.org/abs/2306.16527) — 交错网络语料库。
- [Jaegle 等人 — Perceiver IO (arXiv:2107.14795)](https://arxiv.org/abs/2107.14795) — 通用 Perceiver 架构。
- [Li 等人 — Otter (arXiv:2305.03726)](https://arxiv.org/abs/2305.03726) — 指令微调的 Flamingo 后裔。
- [Laurençon 等人 — Idefics2 (arXiv:2405.02246)](https://arxiv.org/abs/2405.02246) — Flamingo 方法的现代简化版。