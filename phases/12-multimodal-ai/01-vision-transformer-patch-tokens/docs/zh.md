# Vision Transformer 与 Patch-Token 原语

> 在任何多模态操作之前，图像必须先变成 Transformer 可以消化的 token 序列。2020 年的 ViT 论文用 16×16 像素 patch、线性投影和位置嵌入解决了这个问题。五年后的 2026 年，每款前沿模型（Claude Opus 4.7 原生支持 2576px、Gemini 3.1 Pro、Qwen3.5-Omni）仍然以这种方式起步——编码器从 ViT 演进到 DINOv2 再到 SigLIP 2，加入了 register token，位置编码方案变成了 2D-RoPE，但核心原语始终不变。本课将端到端地剖析 patch-token 流水线，并用 Python 标准库实现它，为 Phase 12 后续课程建立"视觉 token"的具体心智模型。

**类型：** Learn
**语言：** Python（标准库，patch tokenizer + 几何计算器）
**前置课程：** Phase 7（Transformers）、Phase 4（Computer Vision）
**时间：** ~120 分钟

## 学习目标

- 将 H×W×3 的图像转换为带有正确位置编码的 patch token 序列。
- 计算给定（patch 大小、分辨率、隐藏维度、深度）的 ViT 的序列长度、参数量和 FLOPs。
- 说出将 ViT 从 2020 年研究带到 2026 年生产的三项升级：自监督预训练（DINO / MAE）、register token 和原生分辨率打包。
- 在 CLS 池化、均值池化和 register token 之间为下游任务做出选择。

## 问题

Transformer 在向量序列上运行。文本本身就是一个序列（字节或 token）。图像是一个带有三个颜色通道的二维像素网格——不是序列。如果将每个像素展平，一张 224×224 的 RGB 图像会变成 150,528 个 token，在这个长度上做自注意力是不可行的（序列长度的二次方复杂度）。

2020 年之前的做法是在前面加一个 CNN 特征提取器：ResNet 生成一个 7×7 的 2048 维向量特征图，将这 49 个 token 输入 Transformer。这种方法可行，但继承了 CNN 的归纳偏置（平移等变性、局部感受野），且失去了 Transformer 对规模的渴望。

Dosovitskiy 等人（2020）提出了一个直截了当的问题：如果跳过 CNN 会怎样？将图像分割成固定大小的 patch（比如 16×16 像素），通过线性投影将每个 patch 映射为一个向量，添加位置嵌入，然后将序列输入一个标准 Transformer。这在当时是异端——没有卷积的视觉。凭借足够的数据（JFT-300M，然后是 LAION），它在 ImageNet 上击败了 ResNet，并持续改进。

到 2026 年，ViT 原语是无可争议的基础。每个开源权重 VLM 的视觉塔都是它的某种后代（DINOv2、SigLIP 2、CLIP、EVA、InternViT）。问题不再是"是否应该使用 patch？"，而是"什么 patch 大小、什么分辨率调度、什么预训练目标、什么位置编码"。

## 概念

### Patch 即 token

给定一张形状为 `(H, W, 3)` 的图像 `x` 和 patch 大小 `P`，你将图像切割成 `(H/P) × (W/P)` 个不重叠的 patch。每个 patch 是一个 `P × P × 3` 的像素立方体。将每个立方体展平为 `3P²` 的向量。应用形状为 `(3P², D)` 的共享线性投影 `W_E`，将每个 patch 映射到模型的隐藏维度 `D`。

对于 ViT-B/16 的标准配置：
- 分辨率 224，patch 大小 16 → 网格 14×14 → 196 个 patch token。
- 每个 patch 为 `16 × 16 × 3 = 768` 个像素值，投影到 `D = 768`。
- 添加一个可学习的 `[CLS]` token → 序列长度 197。

patch 投影在数学上等价于一个二维卷积，核大小为 `P`，步幅为 `P`，输出通道数为 `D`。这就是生产代码的实际实现方式——`nn.Conv2d(3, D, kernel_size=P, stride=P)`。"线性投影"是概念性表述；"卷积核"是高效实现。

### 位置嵌入（Positional Embedding）

patch 本身没有内在顺序——Transformer 将它们视为一个无序集合。早期 ViT 添加了可学习的一维位置嵌入（每个位置一个 768 维向量，共 197 个）。这种方法可行，但会将模型绑定到训练分辨率：如果在推理时改变网格大小，就必须对位置表进行插值。

现代视觉骨干网络使用 2D-RoPE（Qwen2-VL 的 M-RoPE、SigLIP 2 的默认方案）或分解式二维位置编码。2D-RoPE 根据 patch 的（行、列）索引旋转 query 和 key 向量，因此模型从旋转角度推断相对二维位置。无需位置表。模型在推理时可以处理任意网格大小。

### CLS token、池化输出和 Register Token

图像级别的表示是什么？三种选择并存：

1. **`[CLS]` token**。在 patch 序列前面添加一个可学习向量。经过所有 Transformer 层后，CLS token 的隐藏状态即为图像表示。继承自 BERT。原始 ViT 和 CLIP 使用此方案。
2. **均值池化（Mean Pool）**。对 patch token 的输出隐藏状态取平均。SigLIP、DINOv2 和大多数现代 VLM 使用此方案。
3. **Register Token**。Darcet 等人（2023）观察到，没有显式 sink token 的 ViT 在训练过程中会产生高范数的"伪影"patch，劫持自注意力。添加 4-16 个可学习的 register token 可以吸收这种负载，并改善密集预测质量（分割、深度估计）。DINOv2 和 SigLIP 2 都内置了 register token。

选择对下游任务至关重要。CLS 适合分类。对于将 patch token 输入 LLM 的 VLM，则完全跳过池化——每个 patch 都成为一个 LLM 输入 token。Register token 在交接给 LLM 之前会被丢弃（它们是脚手架，不是内容）。

### 预训练：监督式、对比式、掩码式、自蒸馏式

2020 年的 ViT 使用 JFT-300M 上的监督分类进行预训练。很快被以下方法取代：

- **CLIP（2021）**：在 4 亿图文对上进行对比学习。详见课程 12.02。
- **MAE（2021，He 等人）**：掩码 75% 的 patch，重建像素。自监督，仅需纯图像。
- **DINO（2021）/ DINOv2（2023）**：学生-教师自蒸馏，无需标签，无需标注。2023 年的 DINOv2 ViT-g/14 是最强的纯视觉骨干网络，是"密集特征"用例的默认选择。
- **SigLIP / SigLIP 2（2023，2025）**：使用 sigmoid 损失的 CLIP 变体，配合 NaFlex 实现原生宽高比。2026 年开源 VLM 中占主导地位的视觉塔（Qwen、Idefics2、LLaVA-OneVision）。

预训练方式的选择决定了骨干网络擅长什么：CLIP/SigLIP 适合与文本的语义匹配，DINOv2 适合密集视觉特征，MAE 适合作为下游微调的起点。

### 缩放定律（Scaling Laws）

ViT 缩放（Zhai 等人 2022）确立了 ViT 的质量在模型大小、数据量和计算量方面遵循可预测的规律。在固定计算量下：
- 更大的模型 + 更多数据 → 更好的质量。
- Patch 大小是序列长度与保真度之间的杠杆。Patch 14（DINOv2/SigLIP SO400m 的典型选择）比 patch 16 每张图像产生更多 token；对 OCR 和密集任务更好，但速度更慢。
- 分辨率是另一个重要杠杆。从 224 到 384 到 512 几乎总是有帮助的，代价是 FLOPs 的二次方增长。

ViT-g/14（10 亿参数，patch 14，分辨率 224 → 256 个 token）和 SigLIP SO400m/14（4 亿参数，patch 14）是 2026 年开源 VLM 的两个主力编码器。

### ViT 参数量计算

完整计算在 `code/main.py` 中。对于 ViT-B/16 在 224 分辨率下：

```
patch_embed = 3 * 16 * 16 * 768 + 768  =  591k
cls + pos    = 768 + 197 * 768          =  152k
block        = 4 * 768^2 (QKVO) + 2 * 4 * 768^2 (MLP) + 2 * 2*768 (LN)
             = 12 * 768^2 + 3k          =  7.1M
12 blocks    = 85M
final LN    = 1.5k
total       ≈ 86M
```

在加载 checkpoint 之前，用这种方式估算每个 ViT 的参数量。骨干网络的大小决定了任何下游 VLM 的显存（VRAM）下限。

### 2026 年生产配置

2026 年大多数开源 VLM 配备的编码器是 SigLIP 2 SO400m/14，支持原生分辨率（NaFlex）。它具有：
- 4 亿参数。
- Patch 大小 14，默认分辨率 384 → 每张图像 729 个 patch token。
- 图像级任务使用均值池化；VQA 任务中所有 729 个 patch 流入 LLM。
- 4 个 register token，在 LLM 交接前丢弃。
- 带有图像级缩放的 2D-RoPE，支持原生宽高比。

该配置中的每个决策都可以追溯到一篇你可以阅读的论文。

## 使用它

`code/main.py` 是一个 patch tokenizer 和几何计算器。它接收（图像 H、W、patch P、隐藏维度 D、深度 L）并报告：

- patch 后的网格形状和序列长度。
- 一个合成 8×8 像素玩具图像的 token 序列（演示展平 + 投影路径）。
- 按 patch 嵌入、位置嵌入、Transformer 块和头部分类的参数量。
- 目标分辨率下每次前向传播的 FLOPs。
- ViT-B/16 @ 224、ViT-L/14 @ 336、DINOv2 ViT-g/14 @ 224、SigLIP SO400m/14 @ 384 的对比表。

运行它。将参数量与已发布的数字进行对比。尝试不同的 patch 大小和分辨率，感受 token 数量的代价。

## 产出

本课生成 `outputs/skill-patch-geometry-reader.md`。给定一个 ViT 配置（patch 大小、分辨率、隐藏维度、深度），它会生成 token 数量、参数量和 VRAM 估算及理由说明。当你为 VLM 选择视觉骨干网络时使用这个技能——它可以防止"token 爆炸导致 LLM 上下文溢出"的意外。

## 练习

1. 计算 Qwen2.5-VL 在原生 1280×720 输入、patch 大小 14 时的 patch-token 序列长度。与仅使用 CLS 的表示相比如何？

2. 一帧 1080p 画面（1920×1080）在 patch 14 下产生多少个 token？以 30 FPS 播放 5 分钟的视频，总共有多少视觉 token？哪种成本节省最大：池化、帧采样还是 token 合并？

3. 用纯 Python 实现对 patch token 的均值池化。验证对 DINOv2 输出的 196 个 token 做均值池化后，与模型 `forward` 返回的池化嵌入是否一致。

4. 阅读 "Vision Transformers Need Registers"（arXiv:2309.16588）的第 3 节。用两句话描述 register 吸收了什么伪影，以及为什么这对下游密集预测很重要。

5. 修改 `code/main.py` 以支持 patch-n'-pack：给定一组不同分辨率的图像，生成一个打包序列和块对角注意力掩码。到达课程 12.06 时进行验证。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Patch | "16×16 像素方块" | 输入图像的一个固定大小不重叠区域；成为一个 token |
| Patch embedding（Patch 嵌入） | "线性投影" | 一个共享的学习矩阵（或步幅=P 的 Conv2d），将展平的 patch 像素映射到 D 维向量 |
| CLS token | "分类 token" | 前置的可学习向量，其最终隐藏状态代表整张图像；2026 年是可选的 |
| Register token | "Sink token" | 额外的可学习 token，吸收 ViT 在预训练过程中产生的高范数注意力伪影 |
| Position embedding（位置嵌入） | "位置信息" | 每个位置的向量或旋转，使序列具有顺序感知能力；2D-RoPE 是现代默认方案 |
| Grid（网格） | "Patch 网格" | 给定分辨率和 patch 大小下的 (H/P) × (W/P) 二维 patch 数组 |
| NaFlex | "原生灵活分辨率" | SigLIP 2 的特性：单一模型服务多种宽高比和分辨率，无需重新训练 |
| Backbone（骨干网络） | "视觉塔" | 预训练的图像编码器，其 patch-token 输出在 VLM 中馈送给 LLM |
| Pooling（池化） | "图像级摘要" | 将 patch token 转换为单个向量的策略：CLS、均值、注意力池化或基于 register |
| Patch 14 vs 16 | "更细 vs 更粗的网格" | Patch 14 每张图像产生更多 token，OCR 保真度更好，速度更慢；patch 16 是经典默认值 |

## 延伸阅读

- [Dosovitskiy 等人 — An Image is Worth 16x16 Words (arXiv:2010.11929)](https://arxiv.org/abs/2010.11929) — 原始 ViT。
- [He 等人 — Masked Autoencoders Are Scalable Vision Learners (arXiv:2111.06377)](https://arxiv.org/abs/2111.06377) — MAE，自监督预训练。
- [Oquab 等人 — DINOv2 (arXiv:2304.07193)](https://arxiv.org/abs/2304.07193) — 大规模自蒸馏，无需标签。
- [Darcet 等人 — Vision Transformers Need Registers (arXiv:2309.16588)](https://arxiv.org/abs/2309.16588) — register token 与伪影分析。
- [Tschannen 等人 — SigLIP 2 (arXiv:2502.14786)](https://arxiv.org/abs/2502.14786) — 2026 年的默认视觉塔。
- [Zhai 等人 — Scaling Vision Transformers (arXiv:2106.04560)](https://arxiv.org/abs/2106.04560) — 经验性缩放定律。