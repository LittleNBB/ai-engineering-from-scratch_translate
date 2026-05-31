// =============================================================================
// 提示工程（Prompt Engineering）- TypeScript 版本
// 本文件是 prompt_engineering.py 的 TypeScript 镜像实现
// 对应课程文档：phases/11-llm-engineering/01-prompt-engineering/docs/zh.md
// 参考来源：
//   https://platform.openai.com/docs/guides/text-generation
//   https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering
//   https://ai.google.dev/gemini-api/docs/text-generation
//
// 【初学者导读】
// 这个文件和 Python 版本功能完全相同，只是用 TypeScript 重新实现。
// 如果你已经理解了 Python 版本，可以对比学习 TypeScript 的语法差异：
//   - TypeScript 有类型系统（type, interface），能在编译时发现错误
//   - 使用 readonly 保证数据不可变（immutable），更安全
//   - 使用 as const 让对象成为"字面量类型"，获得更精确的类型推断
// =============================================================================

// 【Node.js 内置模块】
// createHash 用于生成 MD5 哈希，和 Python 的 hashlib.md5() 作用相同
import { createHash } from "node:crypto";

// =============================================================================
// 第一部分：类型定义（Type Definitions）
// =============================================================================
// 【TypeScript 的类型系统】
// TypeScript 相比 JavaScript 的最大优势就是"类型系统"。
// 通过定义类型，编辑器可以在你写代码时就告诉你哪里错了，
// 而不是等到运行时才发现问题。
//
// 【PatternName 类型】
// 用"联合类型"（Union Type）限定模式名称只能是这9个字符串之一。
// 如果你写 "persona" 是合法的，但写 "person" 就会报编译错误。
// 这就像 Python 的 Literal["persona", "few_shot", ...]
type PatternName =
  | "persona"
  | "few_shot"
  | "chain_of_thought"
  | "template_fill"
  | "critique"
  | "guardrail"
  | "decomposition"
  | "audience_adapt"
  | "boundary";

// 【Pattern 类型】
// 定义了一个"提示词模式"的数据结构。
// readonly 表示这些属性一旦创建就不能修改（不可变性）。
// 这类似于 Python 中用 dataclass(frozen=True) 的效果。
type Pattern = {
  readonly name: string;           // 模式名称（如 "Persona Pattern"）
  readonly template: string;       // 模板字符串，用 {变量名} 作为占位符
  readonly variables: readonly string[];  // 需要填入的变量列表
  readonly temperature: number;    // 推荐的温度参数（0=确定性，1=创造性）
  readonly description: string;    // 模式的用途说明
};

// =============================================================================
// 提示词模式库（Prompt Pattern Catalog）
// =============================================================================
// 【as const 的作用】
// 加上 as const 后，TypeScript 会把整个对象当作"常量"处理：
// - 所有属性变成 readonly（只读）
// - 字符串值变成字面量类型（如 "persona" 而不是 string）
// - 数组变成只读元组
// 这让 TypeScript 能做更精确的类型检查。
//
// 【10种模式详解】
// 1. persona（角色模式）- 让AI扮演特定角色，激活对应领域知识
// 2. few_shot（少样本）- 给几个示例让AI学会格式
// 3. chain_of_thought（思维链）- 要求AI逐步推理
// 4. template_fill（模板填充）- 从文本提取信息填入模板
// 5. critique（自我批评）- 先生成再自我评审改进
// 6. guardrail（护栏）- 限制AI只回答特定领域问题
// 7. decomposition（分解）- 把大问题拆成小问题
// 8. audience_adapt（受众适配）- 根据受众调整解释方式
// 9. boundary（边界）- 严格限制回答范围
const PROMPT_PATTERNS: Readonly<Record<PatternName, Pattern>> = {
  // --- 角色模式 ---
  // 【原理】"你是Stripe的资深技术作家"这样的描述，会激活模型训练数据中
  // 该领域专家的知识分布，从而产生更专业的回答。
  persona: {
    name: "Persona Pattern",
    template:
      "You are {role} with {experience}.\nYour communication style is {style}.\nYou prioritize {priority}.\n\n{task}",
    variables: ["role", "experience", "style", "priority", "task"],
    temperature: 0.7,
    description: "Activates a specific expert distribution in the training data",
  },

  // --- 少样本模式 ---
  // 【原理】给模型2-3个"输入→输出"的示例，它会从中学习规律，
  // 然后对新的输入生成类似格式的输出。就像教新员工看案例。
  few_shot: {
    name: "Few-Shot Pattern",
    template: "Here are examples of the expected input/output format:\n\n{examples}\n\nNow process this input:\n{input}",
    variables: ["examples", "input"],
    temperature: 0.0,  // 格式化任务需要确定性
    description: "Anchors output format with concrete examples",
  },

  // --- 思维链模式 ---
  // 【原理】强制模型先写出推理过程再给答案，显著提高推理准确率。
  // 就像要求学生"写出解题过程"而不是只写答案。
  chain_of_thought: {
    name: "Chain-of-Thought Pattern",
    template:
      "Think through this step by step.\n\nProblem: {problem}\n\nSteps:\n1. Identify the key components\n2. Analyze each component\n3. Synthesize your findings\n4. State your conclusion\n\nShow your reasoning before the final answer.",
    variables: ["problem"],
    temperature: 0.3,
    description: "Forces explicit reasoning before the final answer",
  },

  // --- 模板填充模式 ---
  // 【原理】给模型一个明确的"表单"让它填写，比自由文本更容易控制和解析。
  template_fill: {
    name: "Template Fill Pattern",
    template:
      "Extract information from the following text and fill in the template.\n\nText: {text}\n\nTemplate:\n{template_structure}\n\nFill every field. If unknown, write 'N/A'.",
    variables: ["text", "template_structure"],
    temperature: 0.0,
    description: "Constrains output to named fields",
  },

  // --- 自我批评模式 ---
  // 【原理】通过"生成→评审→改进"三步流程，模型能发现自身不足并修正。
  critique: {
    name: "Critique Pattern",
    template:
      "Task: {task}\n\nStep 1: Generate an initial response.\nStep 2: Critique it for accuracy, completeness, and clarity.\nStep 3: Produce an improved final version.\n\nLabel each step clearly.",
    variables: ["task"],
    temperature: 0.5,
    description: "Self-refinement through explicit critique",
  },

  // --- 护栏模式 ---
  // 【原理】通过明确规则设定边界，防止AI回答不该回答的问题。
  guardrail: {
    name: "Guardrail Pattern",
    template:
      "You are a {role}.\n\nRules:\n- ONLY answer questions about {domain}\n- If outside {domain}, say: 'This is outside my scope.'\n- NEVER make up information. If unsure, say 'I don't know.'\n- {additional_rules}\n\nUser question: {question}",
    variables: ["role", "domain", "additional_rules", "question"],
    temperature: 0.3,
    description: "Constrains to a domain with explicit boundaries",
  },

  // --- 分解模式 ---
  // 【原理】大问题容易让模型"迷路"，拆成小问题更容易准确回答。
  decomposition: {
    name: "Decomposition Pattern",
    template:
      "Problem: {problem}\n\nBreak this into sub-problems:\n1. List each sub-problem\n2. Solve each independently\n3. Combine sub-solutions into a final answer\n4. Verify the final answer against the original problem",
    variables: ["problem"],
    temperature: 0.3,
    description: "Breaks complex problems into manageable pieces",
  },

  // --- 受众适配模式 ---
  // 【原理】根据目标受众自动调整用词复杂度和举例方式。
  audience_adapt: {
    name: "Audience Adaptation Pattern",
    template:
      "Explain {concept} for the following audience: {audience}.\n\nConstraints:\n- Vocabulary appropriate for {audience}\n- Length: {length}\n- Include {include}\n- Exclude {exclude}",
    variables: ["concept", "audience", "length", "include", "exclude"],
    temperature: 0.5,
    description: "Adapts explanation to the target audience",
  },

  // --- 边界模式 ---
  // 【原理】比护栏模式更"硬"——超出范围直接给出固定的拒绝话术。
  boundary: {
    name: "Boundary Pattern",
    template:
      "You are an assistant that ONLY handles {scope}.\n\nIf the request is in scope, help fully.\nIf out of scope, respond exactly with:\n'{refusal_message}'\n\nDo not attempt to answer out-of-scope questions.\n\nUser: {user_input}",
    variables: ["scope", "refusal_message", "user_input"],
    temperature: 0.0,
    description: "Hard boundary on what the model responds to",
  },
} as const;

// =============================================================================
// 第二部分：模型配置类型和数据
// =============================================================================
// 【Provider 类型】
// 限定只能是三个主流AI提供商之一。
type Provider = "openai" | "anthropic" | "google";

// 【ModelConfig 类型】
// 每个模型的配置信息。
type ModelConfig = {
  readonly provider: Provider;       // 提供商名称
  readonly model: string;            // 模型标识符（API中使用的名称）
  readonly maxTokens: number;        // 最大输出token数
  readonly contextWindow: number;    // 上下文窗口大小（能处理的总token数）
};

// 三个主流模型的配置
// 注意：Google Gemini 的上下文窗口高达 200万 tokens，远超其他模型
const MODEL_CONFIGS: Readonly<Record<string, ModelConfig>> = {
  "gpt-4o": { provider: "openai", model: "gpt-4o", maxTokens: 2048, contextWindow: 128_000 },
  "claude-3.5-sonnet": { provider: "anthropic", model: "claude-3-5-sonnet-20241022", maxTokens: 2048, contextWindow: 200_000 },
  "gemini-1.5-pro": { provider: "google", model: "gemini-1.5-pro", maxTokens: 2048, contextWindow: 2_000_000 },
};

// =============================================================================
// 第三部分：提示词构建器（Prompt Builder）
// =============================================================================
// 【BuiltPrompt 类型】
// 构建好的提示词对象，包含发送给API所需的所有信息。
type BuiltPrompt = {
  readonly system: string;       // 系统消息：设定AI的角色和规则
  readonly user: string;         // 用户消息：实际的任务指令
  readonly temperature: number;  // 温度参数
  readonly pattern: PatternName; // 使用的模式名称
  readonly metadata: { description: string; variablesUsed: readonly string[] };  // 元数据
};

// 【renderTemplate 函数】
// 将模板字符串中的 {变量名} 替换为实际值。
// 例如: "You are {role}" + {role: "医生"} -> "You are 医生"
//
// 【工作原理】
// 用正则表达式 /\{(\w+)\}/g 匹配所有 {变量名} 的模式：
//   \{  - 匹配左花括号
//   (\w+) - 捕获一个或多个字母数字字符（变量名）
//   \}  - 匹配右花括号
//   g   - 全局匹配（替换所有匹配项，不只是第一个）
//
// 对于每个匹配项，用变量字典中的值替换。
// 如果变量不存在，抛出错误。
function renderTemplate(template: string, vars: Readonly<Record<string, string>>): string {
  return template.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = vars[name];
    if (value === undefined) throw new Error("Missing template variable: " + name);
    return value;
  });
}

// 【buildPrompt 函数】
// 核心构建器：根据模式名称和变量，生成完整的提示词。
//
// 工作流程：
// 1. 从模式库中查找指定模式
// 2. 检查是否提供了所有必要变量
// 3. 将变量填入模板
// 4. 设置系统消息
// 5. 返回完整的提示词对象
function buildPrompt(
  patternName: PatternName,
  variables: Readonly<Record<string, string>>,
  systemOverride?: string,  // 可选：自定义系统消息
): BuiltPrompt {
  const pattern = PROMPT_PATTERNS[patternName];

  // 检查缺失的变量
  const missing = pattern.variables.filter((v) => !(v in variables));
  if (missing.length > 0) {
    throw new Error("Missing variables for " + patternName + ": " + missing.join(","));
  }

  // 填入变量
  const rendered = renderTemplate(pattern.template, variables);

  // 使用自定义系统消息，或生成默认的
  const system = systemOverride ?? "You are an AI assistant using the " + pattern.name + ".";

  return {
    system,
    user: rendered,
    temperature: pattern.temperature,
    pattern: patternName,
    metadata: { description: pattern.description, variablesUsed: Object.keys(variables) },
  };
}

// =============================================================================
// 第四部分：API 请求类型定义和格式化器
// =============================================================================
// 【为什么要定义不同的请求类型？】
// 不同AI提供商的API格式不同，TypeScript的类型系统让我们能在编译时
// 就确保每种请求格式的正确性。
//
// 【OpenAI 格式】
// 系统消息和用户消息都在 messages 数组里，通过 role 区分。
type OpenAIRequest = {
  model: string;
  messages: ReadonlyArray<{ role: "system" | "user"; content: string }>;
  temperature: number;
  max_tokens: number;
};

// 【Anthropic 格式】
// 系统消息是单独的 "system" 字段，不在 messages 里。
type AnthropicRequest = {
  model: string;
  system: string;
  messages: ReadonlyArray<{ role: "user"; content: string }>;
  temperature: number;
  max_tokens: number;
};

// 【Google 格式】
// 用 "contents" 代替 "messages"，用 "parts" 携带文本，
// 用 "generationConfig" 设置生成参数。
type GoogleRequest = {
  model: string;
  contents: ReadonlyArray<{ role: "user"; parts: ReadonlyArray<{ text: string }> }>;
  generationConfig: { temperature: number; maxOutputTokens: number };
};

// 联合类型：三种请求格式中的任意一种
type ProviderRequest = OpenAIRequest | AnthropicRequest | GoogleRequest;

// 【formatOpenAI】
// 将统一的 BuiltPrompt 转换为 OpenAI API 请求格式
function formatOpenAI(p: BuiltPrompt, cfg: ModelConfig): OpenAIRequest {
  return {
    model: cfg.model,
    messages: [
      { role: "system", content: p.system },
      { role: "user", content: p.user },
    ],
    temperature: p.temperature,
    max_tokens: cfg.maxTokens,
  };
}

// 【formatAnthropic】
// 将统一的 BuiltPrompt 转换为 Anthropic API 请求格式
// 注意：system 是顶层字段，不在 messages 里
function formatAnthropic(p: BuiltPrompt, cfg: ModelConfig): AnthropicRequest {
  return {
    model: cfg.model,
    system: p.system,
    messages: [{ role: "user", content: p.user }],
    temperature: p.temperature,
    max_tokens: cfg.maxTokens,
  };
}

// 【formatGoogle】
// 将统一的 BuiltPrompt 转换为 Google Gemini API 请求格式
// 注意：系统消息需要合并到用户消息中（Gemini不直接支持单独的系统消息）
function formatGoogle(p: BuiltPrompt, cfg: ModelConfig): GoogleRequest {
  return {
    model: cfg.model,
    contents: [{ role: "user", parts: [{ text: p.system + "\n\n" + p.user }] }],
    generationConfig: { temperature: p.temperature, maxOutputTokens: cfg.maxTokens },
  };
}

// 【格式化器注册表】
// 这是"策略模式"（Strategy Pattern）的应用：
// 根据提供商名称选择对应的格式化函数。
// 在实际项目中，你可以用这个模式轻松添加新的AI提供商。
const FORMATTERS: Readonly<Record<Provider, (p: BuiltPrompt, c: ModelConfig) => ProviderRequest>> = {
  openai: formatOpenAI,
  anthropic: formatAnthropic,
  google: formatGoogle,
};

// =============================================================================
// 第五部分：模拟LLM调用（Simulated LLM Call）
// =============================================================================
// 【为什么要模拟？】
// 真实调用API需要花钱、需要网络、需要API密钥。
// 模拟调用可以让我们在没有API的情况下测试代码逻辑。
//
// 【MD5哈希的作用】
// 用请求内容生成一个短的"指纹"（前8位），这样不同的请求
// 会产生不同的模拟回复，方便区分和调试。

type SimulatedResponse = {
  response: string;                        // 模型的回答文本
  tokensUsed: { prompt: number; completion: number; total: number };  // token用量
  latencyMs: number;                       // 模拟的API延迟（毫秒）
  finishReason: string;                    // 结束原因
};

function simulateLlmCall(modelName: string, request: ProviderRequest): SimulatedResponse {
  // 用请求内容的MD5哈希前8位作为"指纹"
  const promptHash = createHash("md5").update(JSON.stringify(request)).digest("hex").slice(0, 8);

  const responses: Record<string, SimulatedResponse> = {
    "gpt-4o": {
      response: "[GPT-4o " + promptHash + "] Simulated response. Thorough and well-structured.",
      tokensUsed: { prompt: 150, completion: 45, total: 195 },
      latencyMs: 850,
      finishReason: "stop",
    },
    "claude-3.5-sonnet": {
      response: "[Claude 3.5 Sonnet " + promptHash + "] Simulated response. Direct and precise.",
      tokensUsed: { prompt: 145, completion: 40, total: 185 },
      latencyMs: 720,
      finishReason: "end_turn",  // Anthropic 用 "end_turn" 表示正常结束
    },
    "gemini-1.5-pro": {
      response: "[Gemini 1.5 Pro " + promptHash + "] Simulated response. Comprehensive grounding.",
      tokensUsed: { prompt: 155, completion: 42, total: 197 },
      latencyMs: 900,
      finishReason: "STOP",  // Google 用 "STOP" 表示正常结束
    },
  };

  // 如果是未知模型，返回默认值
  return responses[modelName] ?? {
    response: "Unknown model",
    tokensUsed: { prompt: 0, completion: 0, total: 0 },
    latencyMs: 0,
    finishReason: "unknown",
  };
}

// =============================================================================
// 第六部分：回答评分器（Response Scorer）
// =============================================================================
// 【Criteria 类型】
// 评分标准，所有字段都是可选的：
//   - maxWords: 最大字数限制
//   - requiredKeywords: 必须出现的关键词
//   - forbiddenPhrases: 不能出现的短语
//   - expectedFormat: 期望的输出格式（JSON/要点列表/编号列表）
type Criteria = {
  maxWords?: number;
  requiredKeywords?: readonly string[];
  forbiddenPhrases?: readonly string[];
  expectedFormat?: "json" | "bullet_points" | "numbered_list";
};

// 【Score 类型】
// 评分结果。Mutable<T> 是一个工具类型，把所有 readonly 属性变成可写的。
// 因为我们在函数内部需要逐步构建这个对象。
type Score = {
  wordCount?: number;
  lengthCompliant?: boolean;
  keywordsFound?: readonly string[];
  keywordCoverage?: number;
  forbiddenViolations?: readonly string[];
  noViolations?: boolean;
  formatValid?: boolean;
  compositeScore: number;  // 综合得分（0.0-1.0）
};

// 【Mutable 工具类型】
// TypeScript 的"映射类型"（Mapped Type）：
// {-readonly [K in keyof T]: T[K]} 表示"去掉所有 readonly 修饰符"
// 这样我们就能在函数内部修改对象的属性了。
type Mutable<T> = { -readonly [K in keyof T]: T[K] };

// 【scoreResponse 函数】
// 根据评分标准对模型回答打分。
// 支持4个维度：字数、关键词、禁止短语、格式
function scoreResponse(text: string, criteria: Criteria): Score {
  const lower = text.toLowerCase();
  const score: Mutable<Score> = { compositeScore: 0 };
  const components: number[] = [];  // 收集所有评分子项

  // --- 维度1：字数检查 ---
  if (criteria.maxWords !== undefined) {
    const wc = text.trim().split(/\s+/).length;  // 按空格分割计算单词数
    score.wordCount = wc;
    score.lengthCompliant = wc <= criteria.maxWords;
    components.push(score.lengthCompliant ? 1 : 0);
  }

  // --- 维度2：关键词覆盖率 ---
  // 遍历必要关键词，检查是否出现在回答中（不区分大小写）
  if (criteria.requiredKeywords) {
    const found = criteria.requiredKeywords.filter((kw) => lower.includes(kw.toLowerCase()));
    score.keywordsFound = found;
    score.keywordCoverage = criteria.requiredKeywords.length === 0 ? 1 : found.length / criteria.requiredKeywords.length;
    components.push(score.keywordCoverage);
  }

  // --- 维度3：禁止短语检查 ---
  if (criteria.forbiddenPhrases) {
    const violations = criteria.forbiddenPhrases.filter((p) => lower.includes(p.toLowerCase()));
    score.forbiddenViolations = violations;
    score.noViolations = violations.length === 0;
    components.push(score.noViolations ? 1 : 0);
  }

  // --- 维度4：格式检查 ---
  if (criteria.expectedFormat) {
    if (criteria.expectedFormat === "json") {
      // 尝试解析JSON，成功则格式正确
      try {
        JSON.parse(text);
        score.formatValid = true;
      } catch {
        score.formatValid = false;
      }
    } else if (criteria.expectedFormat === "bullet_points") {
      // 检查是否至少一半的非空行是以列表符号开头的
      const lines = text.split("\n").map((l) => l.trim()).filter((l) => l.length > 0);
      const bullets = lines.filter((l) => /^\s*[-*+•]\s+/.test(l));
      score.formatValid = bullets.length >= lines.length * 0.5;
    } else {
      // 编号列表：检查是否有以数字开头的行
      score.formatValid = /^\d+\./m.test(text);
    }
    components.push(score.formatValid ? 1 : 0);
  }

  // --- 计算综合评分：所有子项的平均值 ---
  score.compositeScore = components.length === 0 ? 0 : components.reduce((a, b) => a + b, 0) / components.length;
  return score;
}

// =============================================================================
// 第七部分：多模型测试运行器和比较器
// =============================================================================
type ModelResult = {
  response: string;       // 模型回答
  tokens: SimulatedResponse["tokensUsed"];  // token用量
  apiLatencyMs: number;   // API延迟
  wallTimeMs: number;     // 实际等待时间
  finishReason: string;   // 结束原因
  requestPayload: ProviderRequest;  // 请求内容（方便调试）
};

// 【runPromptTest 函数】
// 把同一个提示词发送到多个模型，收集结果。
// 这就是"A/B测试"——用同一个输入比较不同模型的表现。
function runPromptTest(prompt: BuiltPrompt, models: readonly string[] = Object.keys(MODEL_CONFIGS)): Record<string, ModelResult> {
  const out: Record<string, ModelResult> = {};
  for (const name of models) {
    const cfg = MODEL_CONFIGS[name];
    if (!cfg) {
      throw new Error("Unknown model: " + name + ". Available models: " + Object.keys(MODEL_CONFIGS).join(", "));
    }
    // 格式化为该提供商的API请求格式
    const request = FORMATTERS[cfg.provider](prompt, cfg);
    const start = Date.now();
    // 调用（模拟的）LLM
    const response = simulateLlmCall(name, request);
    out[name] = {
      response: response.response,
      tokens: response.tokensUsed,
      apiLatencyMs: response.latencyMs,
      wallTimeMs: Date.now() - start,
      finishReason: response.finishReason,
      requestPayload: request,
    };
  }
  return out;
}

// 【compareModels 函数】
// 对每个模型的回答评分，然后按得分排序。
function compareModels(results: Record<string, ModelResult>, criteria: Criteria): Array<{ model: string; score: number; tokens: number; latency: number }> {
  const ranked = Object.entries(results).map(([model, r]) => ({
    model,
    score: scoreResponse(r.response, criteria).compositeScore,
    tokens: r.tokens.total,
    latency: r.apiLatencyMs,
  }));
  // 按得分降序排列
  ranked.sort((a, b) => b.score - a.score);
  return ranked;
}

// =============================================================================
// 第八部分：主函数（Main）
// =============================================================================
// 【main 函数做了什么？】
// 1. 打印所有可用的提示词模式目录
// 2. 演示一个单独的提示词构建和测试
// 3. 运行测试套件，比较不同模式在不同模型上的表现
function main(): void {
  // --- 第1步：展示模式目录 ---
  console.log("=".repeat(60));
  console.log("  PROMPT PATTERN CATALOG");
  console.log("=".repeat(60));
  for (const [name, pattern] of Object.entries(PROMPT_PATTERNS)) {
    console.log("\n  [" + name + "] " + pattern.name);
    console.log("    " + pattern.description);
    console.log("    Variables: " + pattern.variables.join(", "));
    console.log("    Recommended temp: " + pattern.temperature);
  }

  // --- 第2步：单个提示词演示 ---
  console.log("\n" + "=".repeat(60));
  console.log("  SINGLE PROMPT BUILD + TEST");
  console.log("=".repeat(60));

  // 用 persona 模式构建提示词
  // 角色：Netflix的资深DevOps工程师
  // 任务：解释为什么容器编排对微服务很重要
  const prompt = buildPrompt("persona", {
    role: "a senior DevOps engineer at Netflix",
    experience: "8 years of infrastructure automation",
    style: "direct and practical",
    priority: "reliability over speed",
    task: "Explain why container orchestration matters for microservices.",
  });
  console.log("\n  System: " + prompt.system);
  console.log("  Temperature: " + prompt.temperature);

  // 在所有模型上测试
  const results = runPromptTest(prompt);
  for (const [model, r] of Object.entries(results)) {
    console.log("\n  [" + model + "]");
    console.log("    Response: " + r.response.slice(0, 100));
    console.log("    Tokens: " + JSON.stringify(r.tokens));
    console.log("    Latency: " + r.apiLatencyMs + "ms");
  }

  // --- 第3步：测试套件 ---
  // TestCase 类型定义：每个测试用例包含名称、模式、变量和评分标准
  type TestCase = { name: string; pattern: PatternName; variables: Record<string, string>; criteria: Criteria };
  const suite: readonly TestCase[] = [
    // 测试1：角色模式 - 技术写作
    {
      name: "Persona: Technical Writer",
      pattern: "persona",
      variables: {
        role: "a senior technical writer at Stripe",
        experience: "10 years of API documentation",
        style: "precise and example-driven",
        priority: "clarity over comprehensiveness",
        task: "Explain what an API rate limit is and why it exists.",
      },
      criteria: { maxWords: 200, requiredKeywords: ["Simulated"], forbiddenPhrases: ["in conclusion"] },
    },
    // 测试2：思维链模式 - 数学问题
    {
      name: "Chain-of-Thought: Math",
      pattern: "chain_of_thought",
      variables: { problem: "20% discount on $85 vs $10 coupon. Which order saves more?" },
      criteria: { requiredKeywords: ["Simulated"], maxWords: 300 },
    },
    // 测试3：护栏模式 - 受限的Python辅导助手
    {
      name: "Guardrail: Scoped Assistant",
      pattern: "guardrail",
      variables: {
        role: "Python programming tutor",
        domain: "Python programming",
        additional_rules: "Do not write complete solutions.",
        question: "How do I sort a list of dictionaries by a key?",
      },
      criteria: { requiredKeywords: ["Simulated"] },
    },
  ];

  console.log("\n" + "=".repeat(60));
  console.log("  TEST SUITE");
  console.log("=".repeat(60));
  for (const test of suite) {
    const p = buildPrompt(test.pattern, test.variables);
    const rs = runPromptTest(p);
    const ranked = compareModels(rs, test.criteria);
    console.log("\n  Test: " + test.name);
    console.log("  Pattern: " + test.pattern);
    for (const r of ranked) {
      console.log("    " + r.model.padEnd(20) + " score=" + r.score.toFixed(3) + " tokens=" + r.tokens + " latency=" + r.latency + "ms");
    }
  }
}

// 运行主函数
main();