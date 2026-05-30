# LLaVA 与视觉指令微调

> LLaVA（2023 年 4 月）是地球上被复制最多的多模态架构。它用 2 层 MLP 替换了 BLIP-2 的 Q-Former，用朴素的 token 拼接替换了 Flamingo 的门控交叉注意力，并在 GPT-4 从纯文本描述生成的 15.8 万轮视觉指令上训练。2023 年到 2026 年间构建 VLM 的每个从业者都构建了 LLaVA 的某种变体。LLaVA-1.5 添加了 AnyRes。LLaVA-NeXT 提升了分辨率。LLaVA-OneVision 在一个方案中统一了图像、多图像和视频。本课走读方案，实现投影器，并解释为什么"更简单的赢了"。

**类型：** Build
**语言：** Python（标准库，投影器 + 指令模板构建器）
**前置课程：** Phase 12 · 02（CLIP）、Phase 11（LLM Engineering — 指令微调）
**时间：** ~180 分钟

## 学习目标

- 构建一个 2 层 MLP 投影器，将 ViT patch 嵌入（维度 1024）映射到 LLM 的嵌入维度（维度 4096）。
- 走读 LLaVA 两阶段方案：(1) 在 55.8 万描述对上对齐投影器，(2) 在 15.8 万 GPT-4 生成的轮次上进行视觉指令微调。
- 构建一个 LLaVA 格式的提示，包含图像 token 占位符、系统提示和用户/助手轮次。
- 解释为什么社区从 Q-Former 转向 MLP，尽管 Q-Former 在 token 预算上更胜一筹。

## 问题

BLIP-2 的 Q-Former（课程 12.03）将图像压缩为 32 个 token。干净、高效、适合基准测试。但它有两个问题。

首先，Q-Former 是可训练的，但其损失不是最终任务。阶段 1 训练 ITC+ITM+ITG。阶段 2 训练 LM 损失。query 学习某种中间表示，然后 LLM 需要解码。信息在瓶颈处丢失。

其次，Q-Former 需要 1.88 亿参数，在 LLaVA 的 2023 年规模下，你必须与目标 LLM 协同设计。更换 LLM，重新训练 Q-Former。更换视觉编码器，重新训练。每种组合都是一个独立的研发项目。

LLaVA 的答案在简单性上令人尴尬：取 ViT 的 576 个 patch token，每个通过 2 层 MLP（`1024 → 4096 → 4096`），然后将全部 576 个放入 LLM 的输入序列。没有瓶颈。没有在奇怪目标上的阶段 1 预训练。只是在直接 LM 损失上训练 MLP。

数据从哪里来？LLaVA 的第二个洞察：使用 GPT-4（纯文本）生成指令数据。将 COCO 的描述和边界框数据提供给 GPT-4，让它生成对话、描述和复杂推理问题。免费获得 15.8 万轮指令-回复。无需人工标注。

结果：一个在 8 张 A100 上运行一天的 VLM，在 MMMU 上击败了 Flamingo，并发布了社区可以扩展的开源 checkpoint。到 2023 年底已衍生出 50 多个分支。

## 概念

### 架构

LLaVA-1.5 13B：
- 视觉编码器：CLIP ViT-L/14 @ 336（阶段 1 冻结，阶段 2 可选解冻）。
- 投影器：带 GELU 激活的 2 层 MLP，`1024 → 4096 → 4096`。
- LLM：Vicuna-13B（后来是 Llama-3.1-8B）。

图像 + 文本提示的前向传播：

```
img -> ViT -> 576 个维度为 1024 的 patch
patches -> MLP -> 576 个维度为 4096 的 token
prompt: system + "<image>" 占位符 + 用户问题
将 <image> token 替换为 576 个投影后的 token
将完整序列输入 LLM
解码回复
```

图像占据 LLM 上下文的 576 个 token。在 2048 上下文下，留给文本 1472 个 token。在 32k 上下文下，这只是一个四舍五入的误差。

### 阶段 1：投影器对齐

冻结 ViT。冻结 LLM。仅训练 2 层 MLP。数据集：55.8 万图文对（LAION-CC-SBU）。损失：在投影后的图像 token 条件下，对描述进行语言建模。

在 batch 128 下单个 epoch 几小时即可完成。投影器学习将 ViT 空间映射到 LLM 空间。没有任务特定的监督。

### 阶段 2：视觉指令微调

解冻投影器（仍然可训练）。解冻 LLM（通常全部，有时用 LoRA）。在 15.8 万轮视觉指令上训练。

指令数据是关键。Liu 等人通过以下方式生成：
1. 取一张 COCO 图像。
2. 提取文本描述（5 条人工描述 + 边界框列表）。
3. 使用三个提示模板发送给 GPT-4：
   - 对话："生成用户和助手之间关于此图像的来回对话。"
   - 详细描述："给出图像的丰富、详细描述。"
   - 复杂推理："提出一个需要对图像进行推理的问题，然后回答它。"
4. 将 GPT-4 的输出解析为（指令，回复）对。

这些都不直接接触图像——只使用文本描述。GPT-4 会幻觉出合理的图像内容。有一些噪声，但它有效：15.8 万轮足以解锁对话能力。

### 为什么社区复制了这个

- 无需调整阶段 1 特定的损失。全程使用 LM 损失。
- 投影器几小时即可训练完成，而非几天。
- LLM 可以替换（LLaVA-Llama2、LLaVA-Mistral、LLaVA-Llama3），只需重新训练投影器。
- 视觉指令数据流水线使用 GPT-4，可以廉价地为新领域重新生成。

### LLaVA-1.5 和 LLaVA-NeXT

LLaVA-1.5（2023 年 10 月）增加了：
- 学术任务数据（VQA、OKVQA、RefCOCO）混入指令微调。
- 更好的系统提示。
- 2048 → 32k 上下文。

LLaVA-NeXT（2024 年 1 月）增加了：
- AnyRes：将高分辨率图像分割成 2×2 或 1×3 的 336×336 裁剪网格，加上一个全局低分辨率缩略图。每个裁剪变成 576 个 token；每张图像总共约 2880 个视觉 token。OCR 和图表任务大幅提升。
- 更好的指令数据混合，使用 ShareGPT4V（高质量 GPT-4V 描述）。
- 更强的基础 LLM（Mistral-7B、Yi-34B）。

### LLaVA-OneVision

课程 12.08 深入介绍 OneVision。简短版本：相同的投影器，但使用课程学习训练，在一个模型中覆盖单图像、多图像和视频，共享视觉 token 预算。

### 与 Q-Former 的对比

| | Q-Former (BLIP-2) | MLP (LLaVA) |
|---|---|---|
| 每张图像视觉 token | 32 | 576（基础）或 2880（AnyRes） |
| 可训练参数 | 1.88 亿 + LM | 4000 万 + LM |
| 阶段 1 损失 | ITC+ITM+ITG | 仅 LM |
| LLM 替换 | 需要重新训练 | 最小重新训练即可替换 |
| 多图像 | 笨拙 | 自然（拼接） |
| 视频 | 笨拙 | 自然（逐帧拼接） |
| Token 预算 | 小 | 大 |

MLP 在简洁性和 token 灵活性上胜出。Q-Former 在 token 预算上胜出。到 2023 年底，token 预算不再是瓶颈（LLM 上下文增长到 32k-128k+），简洁性占主导。

### 提示格式

```
A chat between a curious human and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the human's questions. USER: <image> Describe this image in detail. ASSISTANT: The image shows ...
```

`<image>` 是占位符 token。在分词之前，它被替换为 576 个视觉 token（或 AnyRes 下的 2880 个）。分词器看到的序列比训练时略长，但 LLM 能处理这种新输入，因为阶段 1 已经教会了它。

### 参数经济学

LLaVA-1.5-7B 分解：
- CLIP ViT-L/14 @ 336：3.03 亿（阶段 1 冻结，阶段 2 通常解冻）。
- 投影器（2×线性层）：约 2200 万可训练。
- Llama-7B：70 亿。
- 总计：73 亿参数。阶段 2 可训练：全部 70 亿 + 2200 万投影器。

阶段 2 训练成本：8×A100 约 20 小时。这是关键数字——一天、一个节点、可复现。这就是 LLaVA 传播的原因。

## 使用它

`code/main.py` 实现了：

1. 纯 Python 中的 2 层 MLP 投影器（维度 16 → 32 → 32 的玩具规模）。
2. 提示构建流水线：系统提示 + `<image>` 替换为 N 个投影 token + 用户轮次 + 助手生成占位符。
3. 可视化 576 个 token 的视觉块在 LLM 上下文中的样子（在 2k / 32k / 128k 上下文中消耗的百分比）。

## 产出

本课生成 `outputs/skill-llava-vibes-eval.md`。给定一个 LLaVA 系列 checkpoint，它运行 10 个提示的直觉评估套件（3 个描述、3 个 VQA、2 个推理、2 个拒绝），并报告人类可读的评分卡。不是基准测试；是确认投影器和 LLM 连接良好的烟雾测试。

## 练习

1. 计算 `1024 → 4096 → 4096` 的 2 层 MLP 投影器的可训练参数量。加上 GELU 和偏置，它占 LLaVA-13B 的比例是多少？

2. 为"拒绝"场景构建一个 LLaVA 提示——图像包含一个私人个体。写出预期的助手回复。为什么 LLaVA 应该零样本拒绝这个请求，需要什么训练数据来强化拒绝？

3. 阅读 LLaVA-NeXT 博客的 AnyRes 部分。计算 1344×672 图像在 AnyRes 下的视觉 token 数量。与 336×336 下的基础 576 个 token 进行对比。

4. LLaVA 阶段 1 投影器使用描述上的 LM 损失训练。如果跳过阶段 1 直接进入阶段 2（视觉指令微调）会怎样？引用 Prismatic VLMs 消融实验（arXiv:2402.07865）获取答案。

5. LLaVA-Instruct-150k 使用 GPT-4 和 COCO 描述生成指令。对于新领域（医学 X 光、卫星图像），描述生成领域指令的四步数据流水线。每一步可能出什么问题？

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Projector（投影器） | "MLP 桥接" | 带 GELU 的 2 层 MLP，将 ViT 维度映射到 LLM 维度 |
| Image token（图像 token） | "<image> 占位符" | 推理前被 N 个投影视觉 token 替换的提示标记 |
| Visual instruction tuning（视觉指令微调） | "LLaVA 阶段 2" | 在 GPT-4 生成的（图像，指令，回复）三元组上训练 |
| Stage 1 alignment（阶段 1 对齐） | "投影器预训练" | 冻结 ViT 和 LLM，用描述上的 LM 损失训练投影器 |
| AnyRes | "多裁剪拼贴" | 将高分辨率图像分割成裁剪网格并拼接每个裁剪的视觉 token |
| LLaVA-Instruct | "GPT-4 生成" | 从 COCO 描述 + GPT-4 合成的 15.8 万指令-回复对 |
| Vision encoder freeze（视觉编码器冻结） | "骨干网络锁定" | CLIP 权重在阶段 1 不更新，阶段 2 有时也不更新 |
| ShareGPT4V | "更好的描述" | GPT-4V 生成的 100 万密集描述，用于更高质量的对齐 |
| VQA | "视觉问答" | 回答关于图像的自由形式问题的任务 |
| Prismatic VLMs | "设计空间论文" | Karamcheti 2024 系统测试投影器和数据选择的消融实验 |

## 延伸阅读

- [Liu 等人 — Visual Instruction Tuning (arXiv:2304.08485)](https://arxiv.org/abs/2304.08485) — LLaVA 论文。
- [Liu 等人 — Improved Baselines with Visual Instruction Tuning (arXiv:2310.03744)](https://arxiv.org/abs/2310.03744) — LLaVA-1.5。
- [Chen 等人 — ShareGPT4V (arXiv:2311.12793)](https://arxiv.org/abs/2311.12793) — 密集描述数据集。
- [Karamcheti 等人 — Prismatic VLMs (arXiv:2402.07865)](https://arxiv.org/abs/2402.07865) — 设计空间消融实验。
- [Li 等人 — LLaVA-OneVision (arXiv:2408.03326)](https://arxiv.org/abs/2408.03326) — 统一单图像、多图像、视频。