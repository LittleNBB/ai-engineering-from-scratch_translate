# Show-o 与离散扩散统一模型

> Transfusion 混合了连续和离散表示。Show-o（Xie 等人，2024 年 8 月）走了另一条路：文本 token 使用因果下一个 token 预测，图像 token 使用 MaskGIT 风格的掩码离散扩散。两者位于一个 Transformer 内部，使用混合注意力掩码。结果在一个骨干网络、每模态一个 tokenizer、一个损失公式（下一个 token 扩展到掩码预测）上统一了 VQA、文本到图像、修复和混合模态生成。本课走读 Show-o 设计——为什么掩码离散扩散是并行的、少步图像生成器——并与 Transfusion 和 Emu3 进行对比。

**类型：** Learn
**语言：** Python（标准库，掩码离散扩散采样器）
**前置课程：** Phase 12 · 13（Transfusion）
**时间：** ~120 分钟

## 学习目标

- 解释掩码离散扩散：均匀掩码 token 然后要求 Transformer 恢复它们的调度。
- 对比并行图像解码（Show-o、MaskGIT）与自回归图像解码（Chameleon、Emu3）在速度和质量上的差异。
- 说出 Show-o 在一个 checkpoint 中处理的三个任务：T2I、VQA、图像修复。
- 选择掩码调度（余弦、线性、截断）并推理其对样本质量的影响。

## 问题

Transfusion 的双损失训练有效但动态更复杂——连续扩散损失与离散 NTP 损失处于不同的数值尺度。平衡损失权重是超参数搜索。架构有效但复杂。

Show-o 的回答：保持两种模态都离散（像 Chameleon 一样），但通过掩码离散扩散而非顺序生成图像。训练目标变成单一的掩码 token 预测，自然地泛化了下一个 token 预测。

## 概念

### 掩码离散扩散（MaskGIT）

原始的 Chang 等人（2022）MaskGIT 技巧很优雅。从完全掩码的图像开始（每个 token 都是特殊的 `<MASK>` id）。每一步，并行预测所有被掩码的 token，然后保留置信度最高的 top-K 预测，重新掩码其余的。经过约 8-16 次迭代，所有 token 都被填入。每步解掩码多少 token 的调度是调优的——余弦调度效果好。

训练很简单：从 [0, 1] 均匀采样掩码比率，将其应用于图像的 VQ token，训练 Transformer 恢复被掩码的 token。这正是 BERT 对文本所做的，扩展到了图像生成。

### Show-o：一个 Transformer，混合掩码

Show-o 将 MaskGIT 放入因果语言模型 Transformer 内部。注意力掩码是：

- 文本 token：因果的（标准 LLM）。
- 图像 token：图像块内完全双向（这样被掩码的 token 在预测时可以看到所有其他图像 token）。
- 文本到图像：文本关注前面的图像，图像关注前面的文本。

训练在以下之间交替：
1. 文本序列上的标准 NTP。
2. T2I 样本：文本 → 带掩码图像 token 的图像，掩码 token 预测损失。
3. VQA 样本：图像 → 带掩码文本 token 的文本（实际上就是 NTP）。

统一损失是 `<MASK>` token 上的交叉熵，涵盖了文本 NTP（只有最后一个 token 是"被掩码的"）和图像掩码扩散（随机子集被掩码）。

### 并行采样

Show-o 在约 16 步内生成图像，而非约 1000 步（逐 token 自回归）或约 20 步（扩散）。每一步，并行预测所有被掩码的 token；提交置信度最高的 top-K；重复。

对比：
- Chameleon / Emu3（token 上自回归）：N_tokens 次前向传播，每张图像通常 1024-4096 次。
- Transfusion（连续扩散）：约 20 步，每步一次完整的 Transformer 传播。
- Show-o（掩码离散扩散）：约 16 步，每步一次完整的 Transformer 传播。

Show-o 在相似规模模型下比 Chameleon 更快，步数大致匹配 Transfusion，每步成本更低（离散词汇 logits vs 连续 MSE 损失）。

### 一个 checkpoint 中的任务

Show-o 在推理时支持四种任务，由提示格式选择：

- **文本生成**：标准自回归文本输出。
- **VQA**：图像输入，文本输出。
- **T2I**：文本输入，通过掩码离散扩散输出图像。
- **修复（Inpainting）**：部分 token 被掩码的图像，填充缺失部分。

修复能力从掩码预测训练中免费获得。掩码 VQ-token 网格的一个区域，将其余部分加上文本提示一起输入，预测被掩码的 token。

### 掩码调度

每步解掩码多少 token 的调度影响质量。Show-o 推荐余弦：

```
mask_ratio(t) = cos(pi * t / (2 * T))   # t = 0..T
```

步骤 0 时，所有 token 被掩码（比率 1.0）。步骤 T 时，无掩码。余弦将质量集中在中间范围的比率上，预测在此处最具信息量。线性调度也可行但饱和更快。

### Show-o2

Show-o2（2025 后续，arXiv 2506.15564）扩展了 Show-o：更大的 LLM 基座、更好的 tokenizer、改进的掩码调度。相同的架构模式。

### Show-o 的定位

在 2026 年的分类法中：

- **离散 token + NTP**：Chameleon、Emu3。简单但推理慢。
- **离散 token + 掩码扩散**：Show-o、MaskGIT、LlamaGen、Muse。并行采样，仍受 tokenizer 有损限制。
- **连续 + 扩散**：Transfusion、MMDiT、DiT。最高质量，训练更复杂。
- **连续 + VLM 中的流匹配**：JanusFlow、InternVL-U。最新。

按任务选择：当你想要 T2I + 修复 + VQA 在一个开源模型中且速度合理时选 Show-o；当质量至上且你能承受双损失管道时选 Transfusion。

## 使用它

`code/main.py` 模拟 Show-o 采样：

- 一个 16 个 VQ token 的玩具网格。
- 一个基于提示和当前未掩码 token 预测 logits 的模拟"Transformer"。
- 8 步余弦调度的并行掩码采样。
- 打印中间状态（掩码模式演变）和最终 token。

运行它，观察掩码逐步消融。

## 产出

本课生成 `outputs/skill-unified-gen-model-picker.md`。给定一个同时需要理解（VQA、描述）和生成（T2I、修复）且有开源权重约束的产品，在 Show-o 系列、Transfusion/MMDiT 系列和 Emu3/Chameleon 系列之间做出具体权衡的选择。

## 练习

1. 掩码离散扩散在约 16 步内采样。为什么不是 1 步？如果在步骤 0 就解掩码所有内容会怎样？

2. 修复对掩码扩散是免费的。提出一个产品用例（真实或假设），其中 Show-o 的修复胜过专家模型。

3. 余弦调度 vs 线性调度：追踪 T=8 时每步的未掩码 token 数量。哪个更平衡？

4. 一张 512×512 的 Show-o 图像是 1024 个 token。在词汇表 K=16384 下，模型发出 1024 × log2(16384) = 14,336 位（约 1.75 KiB）的数据。Stable Diffusion 输出 512×512×24 位 = 6,291,456 位（约 768 KiB）的原始像素。压缩比是多少，它买到了什么质量？

5. 阅读 LlamaGen（arXiv:2406.06525）。LlamaGen 的类条件自回归图像模型与 Show-o 的掩码方法有何不同？

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Masked discrete diffusion（掩码离散扩散） | "MaskGIT 风格" | 训练预测被掩码的 token；推理时迭代解掩码最自信的预测 |
| Cosine schedule（余弦调度） | "解掩码调度" | 推理步骤中掩码比率的衰减；将置信度增长集中在中间范围 |
| Parallel decoding（并行解码） | "所有 token 一次" | 每步在一次前向传播中预测完整的被掩码 token 序列，然后提交 top-K |
| Hybrid attention（混合注意力） | "因果 + 双向" | 文本 token 上因果、图像块内双向的掩码 |
| Inpainting（修复） | "填充生成" | 以部分 token 被掩码的图像为条件，预测缺失部分；从训练目标中免费获得 |
| Commitment rate（承诺率） | "每步 top-K" | 每次迭代有多少 token 被宣布"完成"；控制推理 vs 质量的权衡 |

## 延伸阅读

- [Xie 等人 — Show-o (arXiv:2408.12528)](https://arxiv.org/abs/2408.12528)
- [Show-o2 (arXiv:2506.15564)](https://arxiv.org/abs/2506.15564)
- [Chang 等人 — MaskGIT (arXiv:2202.04200)](https://arxiv.org/abs/2202.04200)
- [Sun 等人 — LlamaGen (arXiv:2406.06525)](https://arxiv.org/abs/2406.06525)
- [Chang 等人 — Muse (arXiv:2301.00704)](https://arxiv.org/abs/2301.00704)