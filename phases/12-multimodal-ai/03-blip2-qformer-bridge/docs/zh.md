# 从 CLIP 到 BLIP-2 — Q-Former 作为模态桥接器

> CLIP 对齐了图像和文本，但无法生成描述、回答问题或进行对话。BLIP-2（Salesforce，2023）用一个小型可训练桥接器解决了这个问题：32 个可学习的 query 向量通过交叉注意力关注冻结 ViT 的特征，然后直接插入冻结 LLM 的输入流。1.88 亿参数的桥接器将 110 亿参数的 LLM 连接到 ViT-g/14。截至 2026 年，每一个基于适配器的 VLM——MiniGPT-4、InstructBLIP、LLaVA 的亲族——都是它的后代。本课解读 Q-Former 的架构，解释其两阶段训练，并构建一个将视觉 token 输入冻结文本解码器的玩具版本。

**类型：** Build
**语言：** Python（标准库，交叉注意力 + 可学习 query 演示）
**前置课程：** Phase 12 · 02（CLIP）、Phase 7（Transformers）
**时间：** ~180 分钟

## 学习目标

- 解释为什么在冻结视觉编码器和冻结 LLM 之间的可训练瓶颈在成本和稳定性上优于端到端微调。
- 实现一个交叉注意力模块，其中一组固定的可学习 query 关注外部图像特征。
- 走读 BLIP-2 的两阶段预训练：表示学习（ITC + ITM + ITG）然后生成式学习（使用冻结解码器的 LM 损失）。
- 将 Q-Former 与 LLaVA 使用的更简单的 MLP 投影器进行对比，论证各自的适用场景。

## 问题

你有一个冻结的 ViT，每张图像产生 256 个维度为 1408 的 patch token。你有一个冻结的 7B LLM，期望维度为 4096 的 token 嵌入。最显而易见的桥接——一个从 1408 到 4096 的线性层——可行，但将所有 256 个 patch token 输入 LLM 的上下文会消耗每张图像 256 个额外 token。在一个 32 张图像的 batch 中，仅视觉模态就消耗了 8192 个 token。

BLIP-2 的问题是：你能将 256 个 token 的图像表示压缩到少得多的 token（比如 32 个），同时保留足够的信息让 LLM 生成描述、回答问题和推理图像吗？而且你能在不触及冻结骨干网络的情况下训练这个桥接器，将训练成本控制在仅桥接器的参数范围内吗？

答案是：Q-Former。32 个可学习的"query"向量交叉关注 ViT 的 patch token，产生 32 个视觉 token 的摘要供 LLM 消费。总计 1.88 亿参数。在接触 LLM 之前，用对比式、匹配式和生成式目标进行训练。

## 概念

### 可学习 query

Q-Former 的核心技巧：不是让 LLM 的文本 token 关注图像 patch，而是引入一组新的 32 个可学习 query 向量 `Q`，让*它们*关注图像 patch。这些 query 是模型的参数——在训练期间学习，对每张图像使用相同的 32 个 query。

交叉注意力之后，每个 query 持有图像的压缩摘要——"描述主要物体"、"描述背景"、"计数物体"等。这些 query 并不是字面上专门针对语义标签的；它们学习使下游损失下降所需的任何编码。

### 架构

Q-Former 是一个小型 Transformer（12 层，约 1 亿参数），有两条路径：

1. **Query 路径**：32 个 query 向量通过自注意力（彼此之间），然后对冻结 ViT 的 patch token 做交叉注意力，然后 FFN。
2. **文本路径**：一个类似 BERT 的文本编码器与 query 路径共享自注意力和 FFN 权重。文本路径的交叉注意力被禁用。

训练时两条路径都运行。query 和文本通过共享的自注意力交互，这意味着 query 可以根据文本进行条件化以完成需要文本的任务（ITM、ITG）。VLM 交接推理时，只有 query 流过，产生 32 个视觉 token。

### 两阶段训练

BLIP-2 分两个阶段预训练：

**阶段 1：表示学习（无 LLM）**。三个损失：
- ITC（图文对比）：CLIP 风格的对比损失，在池化的 query token 和文本 CLS token 之间。
- ITM（图文匹配）：二分类器——这对图文是否匹配？硬负样本挖掘。
- ITG（基于图像的文本生成）：文本上的因果 LM 头，以 query 为条件。强制 query 编码可生成文本的内容。

只有 Q-Former 训练。ViT 冻结。不涉及 LLM。

**阶段 2：生成式学习**。接入冻结的 LLM（OPT-2.7B 或 Flan-T5-XL 等）。通过一个小型线性层将 32 个 query 输出投影到 LLM 的嵌入维度。将它们前置到文本提示前。仅训练线性投影和 Q-Former，在拼接的 prompt + image + caption 序列上使用 LM 损失。

阶段 2 之后，Q-Former + 投影层就是完整的视觉适配器。推理时：图像 → ViT → Q-Former → 线性投影 → 前置到文本 → 冻结 LLM 输出。

### 参数经济学

BLIP-2 使用 ViT-g/14（11 亿，冻结）+ OPT-6.7B（67 亿，冻结）+ Q-Former（1.88 亿，训练）= 总计 80 亿，训练 1.88 亿。Q-Former 占整个堆栈参数的约 2.4%。训练成本反映了这一点：在几张 A100 上几天 vs 端到端的几周。

质量：BLIP-2 在零样本 VQA 上匹配或击败 Flamingo-80B，同时小 50 倍。桥接器有效。

### InstructBLIP 和指令感知 Q-Former

InstructBLIP（2023）扩展了 Q-Former，增加了一个额外输入：指令文本本身。在交叉注意力时，query 现在可以访问图像 patch 和指令。query 可以按指令专门化（"数汽车"、"描述氛围"），而不是学习单一固定的摘要。在留出任务上有基准提升。

### MiniGPT-4 和仅投影器方法

MiniGPT-4 保留了 Q-Former，但只训练输出线性投影层，同时冻结其他所有部分。廉价，但代价是质量——query 是 BLIP-2 的，不是你的。适合快速迭代，不是最佳架构。

### 为什么 LLaVA 选择了更简单的方式

LLaVA（2023，课程 12.05）用一个普通的 2 层 MLP 替换了 Q-Former，将每个 ViT patch token 投影到 LLM 空间——24×24 网格的每张图像 576 个 token，全部输入 LLM。压缩更差，但让 LLM 可以直接关注原始 patch。这在当时颇具争议；到 2023 年底它占了主导地位，因为视觉指令数据（LLaVA-Instruct-150k）证明 MLP 可以被训练以保留足够的信号。权衡在于：LLaVA 的上下文填满更快，但它自然地扩展到多图像和视频。

到 2026 年，领域分化：Q-Former 在 token 预算重要的场景（长视频、多图像）中存活；MLP 投影器在每 token 原始质量优先的场景中占主导。

### 门控交叉注意力：Flamingo，祖先

Flamingo（课程 12.04）早于 BLIP-2，使用了相同的交叉注意力思路，但是在冻结 LLM 的每一层都使用，而非作为单一桥接器。BLIP-2 表明你可以仅压缩到输入层并且仍然有效。Gemini 和 Idefics 结合了两者：交错的输入 token 加上可选的门控交叉注意力用于上下文少样本学习。

### 2026 年的后裔

- **Q-Former**：BLIP-2、InstructBLIP、MiniGPT-4，以及大多数视频语言模型出于 token 预算的原因。
- **Perceiver resampler**：Flamingo 的变体（课程 12.04）；Idefics 系列、Eagle、OmniMAE。
- **MLP 投影器**：LLaVA、LLaVA-NeXT、LLaVA-OneVision、Cambrian-1。
- **注意力池化**：VILA、PaliGemma。

四种都是有效的。决定性问题是你受限于 token 预算还是每 token 质量。

## 使用它

`code/main.py` 构建了一个标准库的 Q-Former 风格交叉注意力：

1. 模拟 256 个图像 patch token（维度 128）。
2. 实例化 32 个可学习 query（维度 128）。
3. 运行缩放点积交叉注意力（Q 来自 query，K/V 来自 patch）。
4. 通过线性层投影到 LLM 维度（512）。
5. 输出 32 个 LLM 可用的视觉 token。

所有数学用纯 Python 实现（向量上的嵌套循环）。玩具级但形状正确。注意力权重矩阵会被打印，让你可以看到每个 query 从哪些 patch 中提取信息。

## 产出

本课生成 `outputs/skill-modality-bridge-picker.md`。给定目标 VLM 配置（视觉编码器 token 数量、LLM 上下文预算、部署约束、质量目标），它推荐 Q-Former vs MLP vs Perceiver resampler，并附带简短理由和每种桥接器的参数量估算。

## 练习

1. 在 PyTorch 中实现交叉注意力模块。验证当有 32 个 query 和 256 个 key/value 时，注意力权重矩阵为 32×256，softmax 后每行和为 1。

2. 在 BLIP-2 阶段 1 中，Q-Former 同时运行三个损失：ITC、ITM、ITG。用伪代码写出每个的前向签名。哪一个需要文本编码器路径处于激活状态？

3. 比较参数量：Q-Former（12 层，768 隐藏维度）vs 2 层 MLP 投影器（1408 → 4096，两层）。在什么 LLM 规模下，1.88 亿 Q-Former 的成本能在训练效率上回收？

4. 阅读 BLIP-2 论文（arXiv:2301.12597）第 3.2 节关于 Q-Former 的初始化。解释为什么从 BERT-base 初始化（而非随机初始化）加速收敛。

5. 对于 10 分钟的视频以 1 FPS 采样到 60 帧，计算每帧 token 成本：Q-Former → 32 token/帧 vs MLP 投影器 → 576 token/帧。哪个能放进 128k token 的 LLM 上下文窗口？

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Q-Former | "Querying transformer" | 带有 32 个可学习 query 向量的小型 Transformer，通过交叉注意力关注冻结 ViT 特征 |
| Learnable queries（可学习 query） | "视觉的软提示" | 作为交叉注意力 query 端的一组固定参数；每个模型学习，所有输入共享 |
| Cross-attention（交叉注意力） | "Q 来自这里，K/V 来自那里" | query、key 和 value 来自不同来源的注意力；query 从 ViT patch 中提取信息的方式 |
| ITC | "图文对比" | 应用于 Q-Former 池化 query 与文本 CLS 的 CLIP 风格损失 |
| ITM | "图文匹配" | 基于硬负样本挖掘对的二分类器；强制 query 区分细粒度不匹配 |
| ITG | "基于图像的文本生成" | 以 query 为条件生成文本的因果 LM 损失；强制 query 编码可解码为文本的内容 |
| Two-stage pretraining（两阶段预训练） | "先表示后生成" | 阶段 1 单独训练 Q-Former（ITC/ITM/ITG）；阶段 2 接入冻结 LLM 并仅训练投影层 + Q-Former |
| Frozen backbone（冻结骨干网络） | "不微调" | 视觉编码器和 LLM 权重固定；仅桥接器训练 |
| Projection head（投影头） | "到 LLM 维度的线性层" | 将 Q-Former 输出映射到 LLM 嵌入维度的最终线性层 |
| Perceiver resampler | "Flamingo 的版本" | 类似的可学习 query 交叉注意力，Flamingo 在每一层使用而非作为单一桥接器 |

## 延伸阅读

- [Li 等人 — BLIP-2 (arXiv:2301.12597)](https://arxiv.org/abs/2301.12597) — 核心论文。
- [Li 等人 — BLIP (arXiv:2201.12086)](https://arxiv.org/abs/2201.12086) — 具有 ITC/ITM/ITG 三元组的前身。
- [Li 等人 — ALBEF (arXiv:2107.07651)](https://arxiv.org/abs/2107.07651) — "先对齐后融合"——阶段 1 训练的概念祖先。
- [Dai 等人 — InstructBLIP (arXiv:2305.06500)](https://arxiv.org/abs/2305.06500) — 指令感知 Q-Former。
- [Zhu 等人 — MiniGPT-4 (arXiv:2304.10592)](https://arxiv.org/abs/2304.10592) — 仅投影器方法。
- [Jaegle 等人 — Perceiver IO (arXiv:2107.14795)](https://arxiv.org/abs/2107.14795) — 可学习 query 交叉注意力的通用架构。