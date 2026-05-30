# 任意分辨率视觉：Patch-n'-Pack 与 NaFlex

> 真实图像不是 224×224 的正方形。收据是 9:16，图表是 16:9，医学扫描可能是 4096×4096，手机截图是 9:19.5。2024 年之前 VLM 的答案——将所有东西调整为固定正方形——丢弃了让 OCR、文档理解和高分辨率场景解析得以工作的信号。NaViT（Google，2023）表明你可以将可变分辨率的 patch 打包到单个 Transformer batch 中，配合块对角掩码。Qwen2-VL 的 M-RoPE（2024）完全抛弃了绝对位置表。LLaVA-NeXT 的 AnyRes 将高分辨率图像拼贴为基础图 + 子图。SigLIP 2 的 NaFlex 变体（2025）现在是希望单一 checkpoint 服务每种宽高比的开源 VLM 的默认编码器。本课端到端实现 patch-n'-pack。

**类型：** Build
**语言：** Python（标准库，patch 打包器 + 块对角掩码）
**前置课程：** Phase 12 · 01（ViT patches）、Phase 12 · 05（LLaVA）
**时间：** ~120 分钟

## 学习目标

- 将一批可变分辨率图像的 patch 打包成一个序列，并构建块对角注意力掩码。
- 在 AnyRes 拼贴（LLaVA-NeXT）、NaFlex（SigLIP 2）和 M-RoPE（Qwen2-VL）之间为给定任务做出选择。
- 计算 OCR、图表和摄影在不调整大小情况下的 token 预算。
- 说出正方形调整大小的三种失败模式：文字变形、内容裁剪、token 浪费在填充上。

## 问题

Transformer 期望一个序列。一个 batch 是相同长度的序列的堆叠。如果你的图像是 224×224，你每次都得到 196 个 patch token，无需填充，任务完成。在 224 上训练，在 224 上推理，再也不用考虑分辨率。

世界并不配合。文档是竖版的（8.5×11 英寸，约 2:3）。图表截屏是横版的（16:9）。收据又高又窄（1:3）。医学影像以 2048×2048 或更大尺寸交付。移动设备截屏是 1170×2532（0.46:1）。

2024 年之前的三种选择及各自的失败原因：

1. **调整为固定正方形**（224×224 或 336×336）。拉伸会扭曲文字和人脸。缩小会破坏图表标签和 OCR 内容。直到 LLaVA-1.5 都是标准做法。
2. **裁剪为固定宽高比**。你丢弃了大部分图像，而选择裁剪位置本身就是一个视觉问题。
3. **填充到最长边**。修复了变形，但为竖版图像浪费了 50% 以上的 token 在填充上。所有填充 token 的二次方注意力成本。

2024-2025 年的答案：让 Transformer 以图像的原生分辨率消化 patch，并弄清楚如何将异构 batch 打包成一个序列而不浪费计算。

## 概念

### NaViT 和 patch-n'-pack

NaViT（Dehghani 等人，2023）是证明这在规模上可行的论文。思路是机械式的：

1. 对 batch 中的每张图像，在选定的 patch 大小（比如 14）下计算其原生 patch 网格。
2. 将每张图像的 patch 展平为自己的可变长度序列。
3. 将所有图像的 patch 拼接成 batch 的一个长序列。
4. 构建块对角注意力掩码，使图像 A 的 patch 只在图像 A 内部关注。
5. 携带每个 patch 的位置信息（2D RoPE 或分数位置嵌入）。

一个包含三张图像的 batch：336×336（576 token）、224×224（256 token）和 448×336（768 token）变成一个 1600 token 的序列，配有 1600×1600 的块对角掩码。没有填充。没有浪费的计算。Transformer 处理任意宽高比。

NaViT 还在训练中引入了分数 patch 丢弃——在 batch 中随机丢弃 50% 的 patch——这既起到正则化作用又加速训练。SigLIP 2 继承了这一特性。

### AnyRes（LLaVA-NeXT）

LLaVA-NeXT 的 AnyRes 是务实的替代方案。给定一张高分辨率图像和固定编码器（CLIP 或 SigLIP，336 分辨率），拼贴图像：

1. 从预定义集合中选择最匹配图像宽高比的网格布局——(1×1)、(1×2)、(2×1)、(1×3)、(3×1)、(2×2) 等。
2. 将完整图像拼贴成网格；每个瓦片变成一个 336×336 的裁剪。
3. 同时生成缩略图：将整张图像调整为 336×336 作为全局上下文 token。
4. 通过冻结的 336 编码器编码每个瓦片。拼接瓦片 token + 缩略图 token。

对于 672×672 的图像，2×2 网格加缩略图：4 × 576 + 576 = 2880 个视觉 token。昂贵但有效——LLM 同时看到局部细节和全局上下文。

当你的编码器被冻结且只支持单一分辨率时，AnyRes 是首选路线。它会使大图像的 token 数量爆炸（1344×1344 的图像以 4×4 网格是 9216 + 576 ≈ 9800 个 token，填满了大部分 8k LLM 上下文）。

### M-RoPE（Qwen2-VL）

Qwen2-VL 引入了多模态旋转位置嵌入（Multimodal Rotary Position Embedding）。不同于 NaViT 的分数位置或 AnyRes 的瓦片加缩略图，每个 patch 携带一个 3D 位置（时间、高度、宽度）。query/key 旋转处理任意 H、W 和时间长度。

M-RoPE 原生支持动态分辨率，无需重新训练。推理时你输入任意 H×W 的图像，patch 嵌入器产生 H/14 × W/14 个 token，每个 token 获得其 (t=0, r=row, c=col) 位置，RoPE 以正确的频率旋转注意力，完成。Qwen2.5-VL 和 Qwen3-VL 延续了这一方案。InternVL3 的 V2PE 是相同思路，每种模态有不同的编码。

与 AnyRes 不同，M-RoPE 在原生分辨率下是 O(H×W/P²) 个 token——没有乘法式的瓦片开销。与 NaViT 不同，它仍然期望每次前向传播只有一张图像。跨分辨率的 batch 仍然需要在上面叠加 patch-n'-pack。

### NaFlex（SigLIP 2）

NaFlex 是 SigLIP 2 checkpoint 的原生灵活模式。单一模型在推理时服务多种序列长度（256、729、1024 个 token）。内部使用 NaViT 风格的 patch-n'-pack 训练和每个 patch 的绝对分数位置。卖点是：一个 checkpoint，根据任务在推理时选择 token 预算。

语义任务（分类、检索）用 256 个 token。OCR 或图表理解用 1024 个 token。无需重新训练。

### 打包掩码

块对角掩码是大多数实现出错的地方。对于一个总长度为 `N_total` 的打包序列，覆盖图像 `i=0..B-1`，长度为 `n_i`，形状为 `(N_total, N_total)` 的掩码 `M` 在两个索引落在同一图像的块内时为 1，否则为 0。你可以从累积长度列表构建它：

```
offsets = [0, n_0, n_0+n_1, ..., N_total]
M[i, j] = 1 当且仅当存在 b 使得 offsets[b] <= i < offsets[b+1] 且 offsets[b] <= j < offsets[b+1]
```

在 PyTorch 中这是一行代码，使用 `torch.block_diag` 或显式 gather。FlashAttention 的可变长度路径（`cu_seqlens`）完全跳过掩码，直接使用累积长度 tensor 在序列内进行注意力——对于典型 batch 比密集掩码快约 10 倍。

### Token 预算

按任务选择策略：

- **OCR / 文档**：1024-4096 个 token。SigLIP 2 NaFlex 用 1024，或 AnyRes 3×3 + 缩略图。
- **图表和 UI**：729-1024 个 token，原生 384-448 分辨率。Qwen2.5-VL 动态分辨率配合最大像素上限。
- **自然照片**：256-576 个 token 就够了。下游 LLM 看到的信息足够。在内容密度高的地方才花钱买 token。
- **视频**：空间池化后每帧 64-128 个 token，2-8 FPS。课程 12.17 涵盖此内容。

2026 年的生产规则：为每个任务选择最大像素上限，以原生宽高比编码直到该上限，打包 batch，跳过填充。Qwen2.5-VL 暴露 `min_pixels` 和 `max_pixels` 作为精确的调节旋钮。

## 使用它

`code/main.py` 实现了对一批异构图像的 patch-n'-pack，使用整数像素坐标。它：

- 接收一组 (H, W) 图像尺寸。
- 计算每张图像在 patch 大小 14 下的 patch 序列长度。
- 将它们打包成总长度为 `sum(n_i)` 的一个序列。
- 构建块对角注意力掩码（密集型，便于理解）。
- 比较打包成本 vs 正方形调整和 AnyRes 拼贴。
- 打印混合 batch（收据、图表、截图、照片）的 token 预算表。

运行它。输出的数字就是 2026 年每个开源 VLM 使用 patch-n'-pack 的原因。

## 产出

本课生成 `outputs/skill-resolution-budget-planner.md`。给定混合宽高比的工作负载（OCR、图表、照片、视频帧）和总 token 预算，它选择正确的策略（NaFlex、AnyRes、M-RoPE 或固定正方形）并发出每请求的配置。当你为产品选择 VLM 规模时使用这个技能——它可以防止杀死延迟预算的静默 10 倍 token 爆炸。

## 练习

1. 一张收据是 600×1500（1:2.5）。在 patch 大小 14 下，原生分辨率有多少个 token？正方形调整为 336 后有多少个？哪个在实践中丢失更多 OCR 准确率？

2. 为一个包含四张图像、长度分别为 256、576、729、1024 的 batch 构建块对角掩码。验证注意力矩阵为 2585×2585，且恰好有 `256² + 576² + 729² + 1024²` 个非零条目。

3. 对于 1792×896 的图像在 patch 14 下，比较：(a) 正方形调整为 336 然后编码，(b) AnyRes 2×1 + 缩略图，(c) M-RoPE 原生分辨率。哪个使用最少 token？哪个保留最多细节？

4. 实现分数 patch 丢弃：给定一个打包序列，均匀随机丢弃 50% 的 token，并相应更新块对角掩码。测量掩码稀疏度的变化。

5. 阅读 Qwen2-VL 论文（arXiv:2409.12191）第 3.2 节。用两句话描述 `min_pixels` 和 `max_pixels` 控制什么，以及为什么两个界限都很重要。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Patch-n'-pack | "NaViT 风格打包" | 将来自不同图像的可变长度 patch 序列拼接成一个 batch 维度 |
| Block-diagonal mask（块对角掩码） | "打包掩码" | 将每张图像的 patch 限制为只关注自身而非打包中邻居的注意力掩码 |
| AnyRes | "LLaVA-NeXT 拼贴" | 将高分辨率图像分割成固定大小瓦片网格加全局缩略图；用固定编码器编码每个瓦片 |
| NaFlex | "SigLIP 2 原生灵活" | 单一 SigLIP 2 checkpoint 在推理时服务 256/729/1024 token 预算，无需重新训练 |
| M-RoPE | "多模态 RoPE" | 3D 旋转位置编码（时间、行、列），处理任意 H、W、T，无需位置表 |
| cu_seqlens | "FlashAttention 打包" | FlashAttention varlen 路径使用的累积长度 tensor，替代密集块对角掩码 |
| min_pixels / max_pixels | "分辨率界限" | Qwen2.5-VL 的每请求调节旋钮，限制非常小或非常大输入的 token 数量 |
| Visual token budget（视觉 token 预算） | "每张图像多少 token" | 每张图像发出的 patch token 的大致数量；设定 LLM 的提示预算和注意力成本 |

## 延伸阅读

- [Dehghani 等人 — Patch n' Pack: NaViT (arXiv:2307.06304)](https://arxiv.org/abs/2307.06304)
- [Wang 等人 — Qwen2-VL (arXiv:2409.12191)](https://arxiv.org/abs/2409.12191)
- [Laurençon 等人 — What matters when building vision-language models? (Idefics2, arXiv:2405.02246)](https://arxiv.org/abs/2405.02246)
- [Tschannen 等人 — SigLIP 2 (arXiv:2502.14786)](https://arxiv.org/abs/2502.14786)
- [Qwen Team — Qwen2.5-VL Technical Report (arXiv:2502.13923)](https://arxiv.org/abs/2502.13923)