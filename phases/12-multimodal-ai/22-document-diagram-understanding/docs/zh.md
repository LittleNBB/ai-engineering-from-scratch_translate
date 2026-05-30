# 文档与图表理解

> 文档不是照片。PDF、科学论文、发票或手写表格有布局、表格、图表、脚注、标题和纯图像理解无法捕获的语义结构。VLM 之前的堆栈是流水线：Tesseract OCR + LayoutLMv3 + 表格提取启发式。VLM 浪潮用 OCR-free 模型取代了它——Donut（2022）、Nougat（2023）、DocLLM（2023）——直接输出结构化标记。到 2026 年，前沿就是"将页面图像以 2576px 原生分辨率喂给 Claude Opus 4.7"，结构化标记输出免费获得。本课走读文档 AI 的三个时代弧线。

**类型：** Build
**语言：** Python（标准库，布局感知文档解析器骨架）
**前置课程：** Phase 12 · 05（LLaVA）、Phase 5（NLP）
**时间：** ~180 分钟

## 学习目标

- 解释文档 AI 的三个时代：OCR 流水线、OCR-free、VLM 原生。
- 描述 LayoutLMv3 的三个输入流：文本、布局（bbox）、图像 patch，配合统一掩码。
- 对比 Donut（OCR-free，图像→标记）、Nougat（科学论文→LaTeX）、DocLLM（布局感知生成）、PaliGemma 2（VLM 原生）。
- 为新任务选择文档模型（发票、科学论文、手写表格、中文收据）。

## 问题

"理解这个 PDF"看似简单实则很难。信息存在于：

- 文本内容（90% 的信号）。
- 布局（标题、脚注、侧边栏、双栏格式）。
- 表格（行、列、合并单元格）。
- 图形和图表。
- 手写注释。
- 字体和排版（标题 vs 正文）。

原始 OCR 转储文本并丢失其余部分。关心发票的系统需要知道"Total: $1,245"来自右下角，而非脚注。

## 概念

### 时代 1——OCR 流水线（2021 年前）

经典堆栈：

1. PDF → 每页图像。
2. Tesseract（或商业 OCR）提取文本及每词边界框。
3. 布局分析器识别块（标题、表格、段落）。
4. 表格结构识别器解析表格。
5. 领域规则 + 正则表达式提取字段。

对干净印刷文本有效。在手写、倾斜扫描、复杂表格、非英文脚本上失败。每种失败模式都需要自定义异常路径。

### TrOCR（2021）

TrOCR（Li 等人，arXiv:2109.10282）用在合成 + 真实文本图像上训练的 Transformer 编码器-解码器替换了 Tesseract 的经典 CNN-CTC。在手写和多语言文本上完胜。仍然是流水线（检测器然后 TrOCR 然后布局），但 OCR 步骤大幅改进。

### 时代 2——OCR-free（2022-2023）

第一批 OCR-free 模型说：完全跳过检测，将图像像素直接映射到结构化输出。

**Donut**（Kim 等人，arXiv:2111.15664）：
- 编码器-解码器 Transformer，编码器是 Swin-B。
- 输出是表单理解的 JSON、摘要的 Markdown 或任何任务特定 schema。
- 无 OCR，无布局，无检测。

**Nougat**（Blecher 等人，arXiv:2308.13418）：
- 专门在科学论文上训练。
- 输出是 LaTeX / Markdown。
- 处理方程、多栏布局、图形。
- 每个 arXiv 解析器调用的模型。

这些是专家，不是通才。Donut 在科学论文上失败；Nougat 在发票上失败。

### LayoutLMv3（2022）

另一条轨道。LayoutLMv3（Huang 等人，arXiv:2204.08387）保留 OCR 但添加布局理解：

- 三个输入流：OCR 文本 token、每 token 2D 边界框、图像 patch。
- 跨三种模态的掩码训练目标（掩码文本、掩码 patch、掩码布局）。
- 下游：分类、实体提取、表格 QA。

LayoutLMv3 是基于 OCR 的文档理解的巅峰。在表单和发票上强大。需要上游 OCR。标准化文档基准上的最佳 VLM 前准确率。

### DocLLM（2023）

DocLLM（Wang 等人，arXiv:2401.00908）是 LayoutLM 的生成式兄弟。以布局 token 为条件生成自由形式答案。更适合文档 QA；仍然依赖 OCR 输入。

### 时代 3——VLM 原生（2024+）

2024 年的 VLM 变得足够好以完全取代流水线。将高分辨率的完整页面图像输入 VLM，提问，获得答案。

- LLaVA-NeXT 336 瓦片 AnyRes 对小文档有效。
- Qwen2.5-VL 动态分辨率原生处理 2048+ 像素。
- Claude Opus 4.7 支持 2576px 文档。
- PaliGemma 2（2025 年 4 月）专门针对文档 + 手写训练。

VLM 原生与 OCR 流水线之间的差距迅速缩小。到 2026 年，VLM 原生在以下场景胜出：

- 场景文字（手写 + 印刷，混合脚本）。
- 带合并单元格的复杂表格。
- 嵌入文本的数学方程。
- 带文字注释的图形。

OCR 流水线在以下场景仍然胜出：

- 大规模纯扫描工作负载，每页延迟很重要。
- 流水线可靠性（确定性失败 vs VLM 幻觉）。
- 需要可审计 OCR 输出的受监管环境。

### Claude 4.7 / GPT-5 前沿

在 2576 像素原生输入下，前沿 VLM 以接近人类准确率做文档理解。2026 年初的基准数字：

- DocVQA：Claude 4.7 约 95.1，PaliGemma 2 约 88.4，Nougat 约 77.3，流水线 LayoutLMv3 约 83。
- ChartQA：Claude 4.7 约 92.2，GPT-4V 约 78。
- VisualMRC：Claude 4.7 约 94。

闭源模型差距主要是分辨率和基础 LLM 规模。7B 开源模型落后几分但在追赶。

### 数学方程和 LaTeX 输出

科学论文需要方程的精确 LaTeX 输出。Nougat 在此上训练。用 LaTeX 目标训练的 VLM（Qwen2.5-VL-Math、Nougat 衍生版）产生可用的 LaTeX。没有显式 LaTeX 训练，VLM 产生可读但不精确的转录。

2026 年的科学论文流水线：在 PDF 上链式调用 Nougat，然后在棘手页面上调用 VLM。

### 手写

仍然是最难的子任务。混合印刷 + 手写（医生笔记、填写表格）是 OCR 流水线在成本上仍然击败 VLM 的地方。纯手写 VLM 正在改进（Claude 4.7、PaliGemma 2）。

### 2026 年方案

新的文档 AI 项目：

- **大规模纯印刷发票**：LayoutLMv3 + 规则，成本高效。
- **混合文档**（科学 + 手写 + 表单）：VLM 原生（PaliGemma 2 或 Qwen2.5-VL）。
- **完整 arXiv 摄取**：Nougat 用于数学，VLM 用于图形。
- **受监管**：OCR 流水线 + VLM 验证器用于交叉检查。

## 使用它

`code/main.py`：

- 玩具级布局感知 tokenizer：给定（文本，bbox）对，产生 LayoutLMv3 风格的输入。
- Donut 风格任务 schema 生成器：表单的 JSON 模板。
- 每页 token 预算在 OCR 流水线、Donut、Nougat 和 VLM 原生之间的对比。

## 产出

本课生成 `outputs/skill-document-ai-stack-picker.md`。给定文档 AI 项目（领域、规模、质量、受监管），在 OCR 流水线、OCR-free 专家和 VLM 原生之间选择。

## 练习

1. 你的项目是每天 1000 万张发票。哪个堆栈在不损失准确率的情况下最小化每页成本？

2. 为什么 LayoutLMv3 在表单 QA 上优于纯 CLIP VLM 但在场景文字上表现不佳？bbox 流放弃了什么？

3. Nougat 生成 LaTeX。提出一个 VLM 原生输出在 LaTeX 保真度上击败 Nougat 的测试用例，以及 Nougat 胜出的用例。

4. 阅读 PaliGemma 2 论文（Google，2024）。相比 PaliGemma 1，提升文档准确率的关键训练数据添加是什么？

5. 设计一个受监管安全的混合方案：OCR 流水线为主，VLM 为辅交叉检查。你如何解决分歧？

## 关键术语

| 术语 | 常见说法 | 实际含义 |
|------|---------|---------|
| OCR pipeline（OCR 流水线） | "Tesseract 风格" | 阶段式堆栈：检测→OCR→布局→规则；确定性，脆弱 |
| OCR-free | "Donut 风格" | 跳过显式 OCR 的图像到输出 Transformer；单一模型 |
| Layout-aware（布局感知） | "LayoutLM" | 输入包含每 token 边界框坐标；跨模态统一掩码 |
| VLM-native（VLM 原生） | "前沿 VLM" | 将页面图像直接以高分辨率输入 Claude/GPT/Qwen VLM；无流水线 |
| DocVQA | "文档基准" | 文档 VQA 标准；最多引用的分数 |
| Markup output（标记输出） | "LaTeX / MD" | 结构化输出格式而非自由形式文本；支持下游自动化 |

## 延伸阅读

- [Li 等人 — TrOCR (arXiv:2109.10282)](https://arxiv.org/abs/2109.10282)
- [Blecher 等人 — Nougat (arXiv:2308.13418)](https://arxiv.org/abs/2308.13418)
- [Huang 等人 — LayoutLMv3 (arXiv:2204.08387)](https://arxiv.org/abs/2204.08387)
- [Kim 等人 — Donut (arXiv:2111.15664)](https://arxiv.org/abs/2111.15664)
- [Wang 等人 — DocLLM (arXiv:2401.00908)](https://arxiv.org/abs/2401.00908)