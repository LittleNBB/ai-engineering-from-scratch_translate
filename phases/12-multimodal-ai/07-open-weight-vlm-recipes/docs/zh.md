# 开源权重 VLM 方案：真正重要的是什么

> 2024-2026 年的开源权重 VLM 文献是一片消融实验表格的森林。Apple 的 MM1 测试了图像编码器、连接器和数据混合的 13 种组合。Allen AI 的 Molmo 证明了详细的人工描述胜过 GPT-4V 蒸馏。Cambrian-1 运行了 20 多种编码器对比。Idefics2 形式化了五轴设计空间。Prismatic VLMs 在受控基准上比较了 27 种训练方案。从所有这些噪声中，一小部分结果在各论文中成立：图像编码器比连接器架构更重要，数据混合比两者都重要，而详细的人工描述胜过蒸馏的合成数据。本课解读这些表格，让你不必亲自去读。

**类型：** Learn + lab
**语言：** Python（标准库，消融表格解析器 + 方案选择器）
**前置课程：** Phase 12 · 05（LLaVA 基线）
**时间：** ~180 分钟

## 学习目标

- 说出五轴 VLM 设计空间：图像编码器、连接器、LLM、数据混合、分辨率调度。
- 阅读 MM1 / Idefics2 / Cambrian-1 的消融表格并预测哪个旋钮会影响给定的基准测试。
- 给定计算预算和任务组合，为新 VLM 选择方案（编码器、连接器、数据、分辨率）。
- 解释为什么在相同 token 数下，详细的人工描述胜过 GPT-4V 蒸馏。

## 问题

存在数百个开源权重 VLM。"好"和"最先进"之间的差距大多不在架构。而在于数据、分辨率调度和编码器选择。当模型表现不佳时，知道先转动哪个旋钮可以省去一个 500 万 GPU 小时的错误。

2023 年浪潮（LLaVA-1.5、InstructBLIP、MiniGPT-4）使用描述对预训练 + LLaVA-Instruct-150k。好的基线。MMMU 约 35% 封顶。

2024 年浪潮（MM1、Idefics2、Molmo、Cambrian-1、Prismatic VLMs）运行了详尽的消融实验。结果令人惊讶且实用。

## 概念

### 五轴设计空间

Idefics2（Laurençon 等人，2024）命名了这些轴：

1. **图像编码器**。CLIP ViT-L/14、SigLIP SO400m/14、DINOv2 ViT-g/14、InternViT-6B。编码器在 patch 大小、分辨率和预训练目标上各不相同。
2. **连接器**。MLP（2-4 层）、Q-Former（32 个 query + 交叉注意力）、Perceiver Resampler（64 个 query）、C-Abstractor（卷积 + 双线性池化）。
3. **语言模型**。Llama-3 8B / 70B、Mistral 7B、Phi-3、Gemma-2、Qwen2.5。LLM 大小是主要的参数成本。
4. **训练数据**。描述对（CC3M、LAION）、交错数据（OBELICS、MMC4）、指令数据（LLaVA-Instruct、ShareGPT4V、PixMo、Cauldron）。
5. **分辨率调度**。固定 224/336/448、AnyRes、原生动态。训练期间渐进或恒定。

每个生产 VLM 在每个轴上都做了选择。MMMU 分数的大部分方差由轴 1、4 和 5 解释——而不是由你选择的连接器决定。

### 轴 1：编码器 > 连接器

MM1 第 3.2 节显示：从 CLIP ViT-L/14 换到 SigLIP SO400m/14，MMMU 增加 3 分以上。将连接器从 MLP 换到 Perceiver Resampler，增加不到 1 分。Idefics2 复现了：SigLIP > CLIP，在相同 token 数下 Q-Former ≈ MLP ≈ Perceiver。

Cambrian-1 的"Cambrian 视觉编码器对决"（Tong 等人，2024）在视觉中心基准（CV-Bench）上运行了 20 多种编码器。排行榜顶部是 DINOv2 和 SigLIP 的混合；CLIP 在中间；ImageBind 和 ViT-MAE 更低。从 CLIP ViT-L 到 DINOv2 ViT-g/14 在 CV-Bench 上约 5-7 分的差距。

2026 年开源 VLM 的默认编码器是 SigLIP 2 SO400m/14 用于语义 + 密集特征，有时与 DINOv2 ViT-g/14 特征拼接（Cambrian 的"空间视觉聚合器"就是这么做的）。

### 轴 2：连接器设计无关紧要

MM1、Idefics2、Prismatic 和 MM-Interleaved 都得出了相同的结论：在固定的视觉 token 数下，连接器架构几乎不重要。在均值池化 patch 上的 2 层 MLP 在相同 token 预算下与 32 query 的 Q-Former 相差不到 1 分。

真正重要的是 token 数量。更多视觉 token = 更多 LLM 计算 = 更好的性能直到某个拐点，然后收益递减。每张图像 64 个 token 对 OCR 来说太少。576-1024 个 token 是大多数开源 VLM 的最佳区间。2048 以上仅对文档和图表有帮助。

Q-Former vs MLP 是一个成本问题，而非质量问题：Q-Former 将 token 限制在 32-64 个，无论图像分辨率如何；MLP 发出所有 patch token。对于高分辨率输入，Q-Former 节省 LLM 上下文；对于低分辨率，差异是噪声。

### 轴 3：LLM 大小设定天花板

将 LLM 从 7B 翻倍到 13B 在每篇 VLM 论文中都能可靠地增加 2-4 分 MMMU。在 70B 时大多数基准饱和。VLM 的多模态推理天花板就是 LLM 的文本推理天花板——视觉编码器只能喂信息，不能代为推理。

这就是为什么 Qwen2.5-VL-72B 和 Claude Opus 4.7 在 MMMU-Pro 和 ScreenSpot-Pro 上碾压：语言大脑巨大。7B VLM 无法通过巧妙的连接器设计替代 70B VLM。

### 轴 4：数据——详细的人工描述胜过蒸馏

Molmo + PixMo（Deitke 等人，2024）是 2024 年每个人都应该读的结果。Allen AI 让人工标注者用 1-3 分钟的密集语音转文字方式描述图像，产生了 71.2 万张密集描述的图像。训练数据中完全没有 GPT-4V 蒸馏。

Molmo-72B 在 11 个基准中的 11 个上击败了 Llama-3.2-90B-Vision。差距不是架构——而是描述质量。详细的人工描述每张图像包含比短网络描述多 5-10 倍的信息，且在 GPT-4V 蒸馏会幻觉的地方保持事实准确。

ShareGPT4V（Chen 等人，2023）和 Cauldron（Idefics2）遵循了相同的策略，混合人工 + GPT-4V 描述。趋势很清楚：2026 年前沿，描述密度 > 描述数量 > 蒸馏便利性。

### 轴 5：分辨率及其调度

Idefics2 的消融：384 → 448 增加 1-2 分。448 → 980 配合图像分割（AnyRes）在 OCR 基准上再增加 3-5 分。固定分辨率训练在中等准确率上饱和；分辨率渐进（从 224 开始，到 448 或原生结束）训练更快且最终更高。

Cambrian-1 运行了分辨率 vs token 的权衡：在固定计算下，你可以用较低分辨率获得更多 token 或用较高分辨率获得更少 token。较高分辨率对 OCR 胜出；较低分辨率更多 token 对通用场景理解胜出。

2026 年生产方案：阶段 1 在 384 固定训练，阶段 2 使用动态分辨率最高 1280 用于 OCR 密集任务。

### Prismatic 受控对比

Prismatic VLMs（Karamcheti 等人，2024）是控制了所有轴的论文。相同的 13B LLM，相同的指令数据，相同的评估——每次只变化一个轴。结果：

- 每张图像的视觉 token 数解释了约 60% 的方差。
- 编码器选择解释了约 20%。
- 连接器架构解释了约 5%。
- 其余（数据混合、调度器、学习率）约 15%。

这是一个粗略的分解，但它是文献中"我应该先消融什么"最清晰的答案。

### 2026 年选择器

根据证据，2026 年新项目的默认开源 VLM 方案：

- **编码器**：SigLIP 2 SO400m/14 原生分辨率配合 NaFlex，如需分割/定位则与 DINOv2 ViT-g/14 拼接获取密集特征。
- **连接器**：patch token 上的 2 层 MLP。除非 token 受限否则跳过 Q-Former。
- **LLM**：Qwen2.5 / Llama-3.1 / Gemma 2，成本选 7B，质量选 70B，按目标延迟选择。
- **数据**：PixMo + ShareGPT4V + Cauldron，补充任务特定指令数据。
- **分辨率**：动态（长边最小 256，最大 1280 像素）。
- **调度**：阶段 1 对齐（仅投影器），阶段 2 完全微调，阶段 3 任务特定微调。

这些默认值中的每一个都可追溯到本课末尾引用论文中的实测消融实验。

## 使用它

`code/main.py` 是一个消融表格解析器和方案选择器。它编码了 MM1 和 Idefics2 的消融表格（精简版），让你查询：

- "给定预算 X 和任务 Y，什么方案胜出？"
- "如果我在 7B Llama 上将 SigLIP 换成 CLIP，预期的 MMMU 变化是多少？"
- "为获得 80% 置信度的答案，我应该先消融哪个轴？"

输出是一个排名方案列表，附带预期基准变化和"先消融"建议。

## 产出

本课生成 `outputs/skill-vlm-recipe-picker.md`。给定目标任务组合、计算预算和延迟目标，它发出完整方案（编码器、连接器、LLM、数据混合、分辨率调度），附带为每个选择提供依据的消融实验引用。防止工程师每次新 VLM 项目启动时重新发明 Idefics2 消融表格。

## 练习

1. 阅读 MM1 第 3.2 节。对于固定 2B LLM、5000 万张图像的预算，哪个编码器胜出？答案在 13B LLM 下会反转吗？为什么？

2. Cambrian-1 发现拼接 DINOv2 + SigLIP 在视觉中心基准上优于单独使用任何一个，但在 MMMU 上没有增加信号。预测哪些基准会提升，哪些保持不变。

3. 你的目标是 2B LLM 上的移动端 UI 代理。选择编码器、连接器、分辨率和数据混合。用具体的消融表格为每个选择提供依据。

4. Molmo 提供 4B 和 72B 模型。4B 与闭源 7B VLM 竞争力相当；72B 在 11/11 基准上击败 Llama-3.2-90B-Vision。这告诉你关于 LLM 大小平台期假说的什么？

5. 设计一个消融表格来隔离 7B VLM 上数据混合质量与编码器质量的影响。最少需要多少次训练运行？提出四个轴的设置。

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Ablation（消融） | "转一个旋钮" | 训练多个仅在一个设计空间轴上不同、其余完全相同的运行 |
| Connector（连接器） | "桥接" / "投影器" | 将视觉编码器输出映射到 LLM token 空间的可训练模块（MLP、Q-Former、Perceiver） |
| Detailed human caption（详细人工描述） | "密集描述" | 多句人工撰写的描述（通常 80-300 token），比网络 alt 文本更丰富 |
| Distillation（蒸馏） | "GPT-4V 描述" | 由更强的专有 VLM 生成的训练数据；方便但容易继承幻觉 |
| AnyRes / dynamic res（动态分辨率） | "高分辨率路径" | 通过拼贴或 M-RoPE 传入大于编码器原生分辨率图像的策略 |
| Resolution ramp（分辨率渐进） | "课程学习" | 从低分辨率开始并逐渐增加的训练调度，加速对齐学习 |
| Vision-centric bench（视觉中心基准） | "CV-Bench / BLINK" | 强调细粒度视觉感知而非语言密集推理的评估 |
| PixMo | "Molmo 的数据" | Allen AI 的 71.2 万密集描述图像数据集；人工语音转录为密集描述 |

## 延伸阅读

- [McKinzie 等人 — MM1 (arXiv:2403.09611)](https://arxiv.org/abs/2403.09611)
- [Laurençon 等人 — Idefics2 / What matters building VLMs (arXiv:2405.02246)](https://arxiv.org/abs/2405.02246)
- [Deitke 等人 — Molmo and PixMo (arXiv:2409.17146)](https://arxiv.org/abs/2409.17146)
- [Tong 等人 — Cambrian-1 (arXiv:2406.16860)](https://arxiv.org/abs/2406.16860)
- [Karamcheti 等人 — Prismatic VLMs (arXiv:2402.07865)](https://arxiv.org/abs/2402.07865)