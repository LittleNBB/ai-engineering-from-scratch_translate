# 音频语言模型：从 Whisper 到 Audio Flamingo 3 的弧线

> Whisper（Radford 等人，2022 年 12 月）解决了语音识别——68 万小时弱监督多语言语音、简单的编码器-解码器 Transformer、让每个后续 ASR 发布都引用它的基准。但识别不是推理。询问"这段录音里有什么乐器"或"说话人表达什么情绪"或"第 3 分钟发生了什么"需要音频理解，而非转录。Qwen-Audio、SALMONN、LTU 和 NVIDIA 的 Audio Flamingo 3（AF3，2025 年 7 月）逐步构建了这个堆栈：保留 Whisper 级编码器，接上 Q-former，在音频-文本指令数据上训练，加入思维链推理。本课走读这条弧线。

**类型：** Build
**语言：** Python（标准库，log-Mel 频谱图 + 音频 Q-former 骨架）
**前置课程：** Phase 6（Speech and Audio）、Phase 12 · 03（Q-Former）
**时间：** ~180 分钟

## 学习目标

- 从波形计算 log-Mel 频谱图：加窗、FFT、滤波器组、对数变换。
- 对比编码器选项：Whisper 编码器、BEATs、AF-Whisper 混合体。各自适用场景。
- 构建音频 Q-former：N 个可学习 query 交叉关注频谱图 patch。
- 解释级联式（Whisper 然后 LLM）vs 端到端音频 LLM 训练：为什么端到端在推理上扩展更好。

## 问题

语音识别已被 Whisper 解决。音频 OCR 是商品。但"商品"止于转录。如果模型不能对其听到的内容进行推理——时间、说话人、情绪、音乐结构、环境声音——仅靠转录无法驱动产品功能。

三条明显路线：

1. **级联**：Whisper 转录，LLM 对转录推理。纯语音场景有效。对音乐、环境音频、多说话人重叠、情绪无效。
2. **端到端音频 LLM**：音频编码器直接将音频 token 输入 LLM，跳过转录。保留声学信息（情绪、说话人、环境）。需要新训练数据。
3. **混合**：音频编码器 + 文本解码器，既能转录又能推理。Qwen-Audio 和 Audio Flamingo 选择此路线。

## 概念

### Log-Mel 频谱图：输入特征

每个音频编码器从相同的特征开始：log-Mel 频谱图。

1. 重采样到 16kHz。
2. 25ms 窗口、10ms 跳跃的短时傅里叶变换。
3. 取 FFT 结果的幅度。
4. 应用 Mel 滤波器组（典型 80 个滤波器，对数间隔 0-8000 Hz）以感知频率。
5. 对数压缩（log(1 + x)）以处理动态范围。

结果：形状为 (T, 80) 的二维数组，T 是时间帧数。100 Hz 帧率的 30 秒片段：(3000, 80)。

### Whisper 的编码器

Whisper 的编码器是 12 层 ViT 风格 Transformer，将 log-Mel 频谱图作为时间帧序列处理。输出：每个时间帧一个隐藏状态向量。

对于 ASR，Whisper 的解码器是交叉注意力 Transformer，以编码器输出为条件生成文本 token。标准编码器-解码器。

对于 ALM（音频 LLM），你希望编码器输出作为不同 LLM 的输入。模式：Whisper 编码器冻结，Q-former 可训练，LLM 冻结或微调。

### BEATs 和音频专用编码器

Whisper 在语音主导数据上训练。对音乐和环境音频更弱。

BEATs（Chen 等人，2022）是在 AudioSet 上训练的自监督 Transformer。在相同参数量下比 Whisper 更好地捕获音乐和环境声音。

AF-Whisper（Audio Flamingo 3 的混合体）：拼接 Whisper + BEATs 特征作为音频输入。Whisper 携带语言信号，BEATs 携带声学信号。

### 音频 Q-former

与 BLIP-2 的视觉 Q-former 相同模式。固定数量的可学习 query（通常 32 或 64）交叉关注音频编码器的输出帧。query 成为 LLM 消费的音频 token。

训练对齐阶段：仅 Q-former，在音频-文本对（AudioCaps、Clotho）上使用对比 + 描述损失。指令阶段：端到端，解冻 LLM，在指令数据上训练。

### 弧线——SALMONN、Qwen-Audio、AF3

**SALMONN**（Tang 等人，2023）：Whisper + BEATs + Q-former + LLaMA。第一个具有严肃推理能力的开源音频 LLM。MMAU 基准上约 0.55 综合分。

**Qwen-Audio**（Chu 等人，2023）：类似架构，在更丰富的数据集上训练，针对多轮对话微调。MMAU 约 0.60。

**LTU——Listen, Think, Understand**（Gong 等人，2023）：显式推理数据，聚焦于音频片段上的思维链。更小但更聚焦。

**Audio Flamingo 3**（Goel 等人，2025 年 7 月）：当前开源 SOTA。8B LLM 骨干网络（Qwen2 7B），Whisper-large 编码器拼接 BEATs，64 query Q-former，在 100 万+ 音频-文本指令对上训练。MMAU 0.72，在部分子任务上匹配专有前沿。

AF3 还引入了按需音频思维链：模型可以在最终答案前可选地发出思考 token（"让我先识别乐器：..."）。启用思考后，复杂推理任务准确率提升 3-5 分。

### 级联 vs 端到端

级联流水线：

1. Whisper 将音频转录为文本。
2. LLM 对文本推理。

"总结这个播客"完美有效。以下场景失败：
- "这首歌的情绪是什么？"——情绪在声音中，不在文字中。
- "说话的是 Alice 还是 Bob？"——需要说话人识别。
- "爆炸发生在第几秒？"——时间定位在文本中丢失。
- "这是真实还是生成的音频？"——深度伪造检测需要声学特征。

端到端保留声学信号。Qwen-Audio 和 AF3 原生处理音乐、环境和情绪。

### 2026 年生产方案

对于新的音频理解产品：

- **级联**：如果目标是转录，无音乐，无情绪推断。
- **AF3 / Qwen-Audio 系列**：如果需要音乐、情绪、多说话人或复杂音频推理。

级联更便宜更简单。端到端更强大。

### MMAU——音频推理基准

MMAU（大规模多模态音频理解）是 2024-2025 年的音频推理基准：

- 10,000 个跨语音、音乐、环境声音的音频-文本 QA 对。
- 覆盖分类、时间推理、因果推理、开放性 QA。
- 测试级联流水线系统性缺失的能力。

开源 SOTA（AF3）0.72；专有前沿约 0.78（Gemini 2.5 Pro、Claude Opus 4.7）。差距比 VideoMME 的开源 vs 闭源差距更小，表明音频 LLM 正在成熟。

## 使用它

`code/main.py`：

- 用标准库实现 log-Mel 频谱图计算：加窗、朴素 DFT、Mel 滤波器组。
- 音频 Q-former 骨架：给定编码器输出帧，计算 Q、K、V、注意力，发出 N 个 token。
- 级联 vs 端到端在玩具任务上的对比。

## 产出

本课生成 `outputs/skill-audio-llm-pipeline-picker.md`。给定音频任务（转录、音乐标签、情绪推断、多说话人分离、环境分类），在级联、端到端 AF3 或混合之间选择。

## 练习

1. 计算 16kHz、25ms 窗口、10ms 跳跃、80 个 Mel 频段的 30 秒片段的 log-Mel 频谱图维度。在 48kHz 下如何变化？

2. 为什么 Whisper 在音乐上表现不佳？BEATs 捕获了哪些 Whisper 没有的音频特征？

3. 64 个 query vs 32 个 query 的音频 Q-former：在什么任务复杂度下 64 更划算？32 节省什么？

4. 阅读 AF3 第 4 节关于按需思考。提出三个思维链帮助最大的音频任务。

5. 使用 AF3 的输出实现一个最小化说话人分离流水线。你如何信号说话人变化？

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| Log-Mel spectrogram（log-Mel 频谱图） | "Mel 特征" | 经 Mel 滤波器组后的对数值二维（时间、频率）数组 |
| Audio Q-former | "音频 Perceiver" | 从音频编码器输出到固定长度 query 的交叉注意力瓶颈，馈送给 LLM |
| Cascaded（级联） | "ASR 然后 LLM" | Whisper 转录、文本 LLM 推理的流水线；丢失声学信息 |
| End-to-end（端到端） | "音频 LLM" | 音频特征通过 Q-former 直接进入 LLM；保留声学信号 |
| BEATs | "AudioSet 音频编码器" | 在 AudioSet 上训练的 SSL Transformer；音乐 + 环境声音强势 |
| MMAU | "音频推理基准" | 跨语音、音乐、环境的 10k QA 对；2024 评估标准 |
| On-demand thinking（按需思考） | "音频 CoT" | 模型可在最终答案前可选地发出推理 token，提升准确率 3-5 分 |

## 延伸阅读

- [Radford 等人 — Whisper (arXiv:2212.04356)](https://arxiv.org/abs/2212.04356)
- [Chu 等人 — Qwen-Audio (arXiv:2311.07919)](https://arxiv.org/abs/2311.07919)
- [Goel 等人 — Audio Flamingo 3 (arXiv:2507.08128)](https://arxiv.org/abs/2507.08128)
- [Tang 等人 — SALMONN (arXiv:2310.13289)](https://arxiv.org/abs/2310.13289)
- [Gong 等人 — LTU (arXiv:2305.10790)](https://arxiv.org/abs/2305.10790)