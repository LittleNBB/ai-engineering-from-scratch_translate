# =============================================================================
# 提示工程（Prompt Engineering）：模式库 + 构建器 + 多模型测试工具
# 本文件对应课程文档：phases/11-llm-engineering/01-prompt-engineering/docs/zh.md
# 参考来源：
#   https://platform.openai.com/docs/guides/text-generation
#   https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering
#   https://ai.google.dev/gemini-api/docs/text-generation
# =============================================================================
#
# 【初学者导读】
# 这个文件展示了如何用工程化的方式构建和测试"提示词"（prompt）。
# 提示词就是你发给大语言模型（LLM）的指令，模型会根据这些指令生成回答。
# 提示工程的核心思想：写得越精确，得到的回答就越好。
#
# 本文件的结构：
#   1. PROMPT_PATTERNS  - 10种常用的提示词模式（模板）
#   2. MODEL_CONFIGS    - 3个主流模型的配置信息
#   3. build_prompt()   - 提示词构建器：把模式模板填入变量，生成完整的提示词
#   4. build_multi_turn()- 多轮对话构建器
#   5. format_*_request()- 把提示词格式化为不同API的请求格式（OpenAI/Anthropic/Google）
#   6. simulate_llm_call()- 模拟LLM调用（实际项目中替换为真实API调用）
#   7. score_response()  - 评分器：评估模型回答是否符合预期
#   8. compare_models()  - 比较器：比较不同模型的表现
#   9. run_test_suite()  - 测试套件：运行所有测试用例
#

import json
import time
import hashlib
import re


# =============================================================================
# 第一部分：提示词模式库（Prompt Pattern Catalog）
# =============================================================================
# 【什么是"模式"？】
# 模式就是可复用的提示词模板。就像建筑设计有"设计模式"一样，
# 提示工程也有"提示模式"。每种模式适用于不同类型的场景。
#
# 每个模式包含：
#   - name:        模式的英文名称
#   - template:    模板字符串，用 {变量名} 作为占位符
#   - variables:   需要填入的变量列表
#   - temperature: 推荐的"温度"参数（控制随机性，0=确定性，1=创造性）
#   - description: 模式的用途说明
#
# 【关于 temperature（温度）】
# 想象模型在选择下一个词时，会为每个候选词打分。
# temperature=0 时，永远选得分最高的词（最确定）
# temperature=1 时，按概率随机选词（更有创意，但可能不稳定）

PROMPT_PATTERNS = {
    # --- 模式1：角色模式（Persona Pattern）---
    # 【用途】让模型扮演某个特定角色，比如"资深技术作家"。
    # 【原理】LLM在海量文本上训练过，不同的角色描述会激活模型训练数据中
    #         对应领域的知识。角色越具体，激活的知识越精准。
    # 【示例】"你是Stripe的资深技术作家，有10年API文档经验..."
    "persona": {
        "name": "Persona Pattern",
        "template": (
            "You are {role} with {experience}.\n"
            "Your communication style is {style}.\n"
            "You prioritize {priority}.\n\n"
            "{task}"
        ),
        "variables": ["role", "experience", "style", "priority", "task"],
        "temperature": 0.7,  # 角色扮演需要一些创造性，所以温度稍高
        "description": "Activates a specific expert distribution in the model's training data",
    },

    # --- 模式2：少样本模式（Few-Shot Pattern）---
    # 【用途】给模型几个"输入→输出"的示例，让它学会你期望的格式和风格。
    # 【原理】模型会从示例中学习规律，然后对新的输入生成类似格式的输出。
    #         这就像你给新员工看了3个案例，他就能模仿着做第4个。
    # 【示例】给2个情感分析的例子，然后让模型分析第3条评论
    "few_shot": {
        "name": "Few-Shot Pattern",
        "template": (
            "Here are examples of the expected input/output format:\n\n"
            "{examples}\n\n"
            "Now process this input:\n{input}"
        ),
        "variables": ["examples", "input"],
        "temperature": 0.0,  # 格式化任务需要确定性，温度设为0
        "description": "Provides concrete examples to anchor the output format and style",
    },

    # --- 模式3：思维链模式（Chain-of-Thought Pattern）---
    # 【用途】要求模型"一步一步思考"，先展示推理过程，再给出最终答案。
    # 【原理】强制模型把复杂问题拆解成小步骤，每步都明确写出，
    #         这样能显著提高数学、逻辑推理类任务的准确率。
    #         就像你要求学生"写出解题过程"而不是只写答案。
    # 【示例】"一家店打8折，原价$85，还有$10优惠券，先打折再用券和先用券再打折哪个更划算？"
    "chain_of_thought": {
        "name": "Chain-of-Thought Pattern",
        "template": (
            "Think through this step by step.\n\n"
            "Problem: {problem}\n\n"
            "Steps:\n"
            "1. Identify the key components\n"
            "2. Analyze each component\n"
            "3. Synthesize your findings\n"
            "4. State your conclusion\n\n"
            "Show your reasoning before giving the final answer."
        ),
        "variables": ["problem"],
        "temperature": 0.3,  # 推理任务需要较低的随机性
        "description": "Forces explicit reasoning steps before the final answer",
    },

    # --- 模式4：模板填充模式（Template Fill Pattern）---
    # 【用途】从一段文本中提取信息，填入预定义的模板字段。
    # 【原理】给模型一个明确的"表单"，让它逐项填写。
    #         这比自由文本输出更容易控制和解析。
    # 【示例】从简历文本中提取：姓名、公司、工作年限、学历、专长
    "template_fill": {
        "name": "Template Fill Pattern",
        "template": (
            "Extract information from the following text and fill in the template.\n\n"
            "Text: {text}\n\n"
            "Template:\n{template_structure}\n\n"
            "Fill in every field. If information is not available, write 'N/A'."
        ),
        "variables": ["text", "template_structure"],
        "temperature": 0.0,  # 信息提取需要完全确定性
        "description": "Constrains output to a specific structure with named fields",
    },

    # --- 模式5：自我批评模式（Critique Pattern）---
    # 【用途】让模型先生成回答，然后自我批评，最后给出改进版本。
    # 【原理】通过"生成→评审→改进"的三步流程，模型能发现自己的不足
    #         并修正。这就像你写完作文后自己检查修改一样。
    # 【适用场景】需要高质量输出的任务，如写文章、写代码
    "critique": {
        "name": "Critique Pattern",
        "template": (
            "Task: {task}\n\n"
            "Step 1: Generate an initial response.\n"
            "Step 2: Critique your response for accuracy, completeness, and clarity.\n"
            "Step 3: Produce an improved final version.\n\n"
            "Label each step clearly."
        ),
        "variables": ["task"],
        "temperature": 0.5,
        "description": "Self-refinement through explicit critique before final output",
    },

    # --- 模式6：护栏模式（Guardrail Pattern）---
    # 【用途】限制模型只回答特定领域的问题，超出范围就说"不在我的职责范围内"。
    # 【原理】通过明确的规则设定"边界"，防止模型回答不该回答的问题。
    #         这就像设一个客服只处理退款问题，不回答技术问题。
    # 【重要】这是防止AI"越界"的关键手段
    "guardrail": {
        "name": "Guardrail Pattern",
        "template": (
            "You are a {role}.\n\n"
            "Rules:\n"
            "- ONLY answer questions about {domain}\n"
            "- If the question is outside {domain}, say: 'This is outside my scope.'\n"
            "- NEVER make up information. If unsure, say 'I don't know.'\n"
            "- {additional_rules}\n\n"
            "User question: {question}"
        ),
        "variables": ["role", "domain", "additional_rules", "question"],
        "temperature": 0.3,
        "description": "Constrains the model to a specific domain with explicit boundaries",
    },

    # --- 模式7：元提示模式（Meta-Prompt Pattern）---
    # 【用途】让AI帮你写提示词！你告诉它你的目标，它帮你生成一个优化过的提示词。
    # 【原理】"用AI来优化AI的指令"——这是一种递归的优化策略。
    #         模型知道什么样的提示词效果好，所以它能帮你写出更好的提示词。
    # 【适用场景】当你不知道怎么写提示词时，先让AI帮你写一个草稿
    "meta_prompt": {
        "name": "Meta-Prompt Pattern",
        "template": (
            "Write a prompt for an LLM that will {objective}.\n\n"
            "The prompt should include:\n"
            "- A specific role/persona\n"
            "- Clear constraints and output format\n"
            "- 2-3 few-shot examples\n"
            "- Edge case handling\n\n"
            "Optimize the prompt for {metric}.\n"
            "Target model: {model}."
        ),
        "variables": ["objective", "metric", "model"],
        "temperature": 0.7,
        "description": "Uses the LLM to generate optimized prompts for other tasks",
    },

    # --- 模式8：分解模式（Decomposition Pattern）---
    # 【用途】把复杂问题拆解成小的子问题，逐个解决后再合并。
    # 【原理】大问题容易让模型"迷路"，小问题更容易准确回答。
    #         就像你不会让学生直接做一道综合大题，而是拆成几个小问。
    # 【适用场景】复杂的分析任务、多步骤决策
    "decomposition": {
        "name": "Decomposition Pattern",
        "template": (
            "Problem: {problem}\n\n"
            "Break this into sub-problems:\n"
            "1. List each sub-problem\n"
            "2. Solve each independently\n"
            "3. Combine sub-solutions into a final answer\n"
            "4. Verify the final answer against the original problem"
        ),
        "variables": ["problem"],
        "temperature": 0.3,
        "description": "Breaks complex problems into manageable pieces",
    },

    # --- 模式9：受众适配模式（Audience Adaptation Pattern）---
    # 【用途】针对不同受众调整解释方式（如给10岁小孩 vs 给专家）。
    # 【原理】同样的概念，对不同人需要不同的表达方式。
    #         模型可以自动调整用词复杂度、举例方式等。
    # 【示例】"向5岁小孩解释量子力学" vs "向物理学教授解释量子力学"
    "audience_adapt": {
        "name": "Audience Adaptation Pattern",
        "template": (
            "Explain {concept} for the following audience: {audience}.\n\n"
            "Constraints:\n"
            "- Use vocabulary appropriate for {audience}\n"
            "- Length: {length}\n"
            "- Include {include}\n"
            "- Exclude {exclude}"
        ),
        "variables": ["concept", "audience", "length", "include", "exclude"],
        "temperature": 0.5,
        "description": "Adapts explanation complexity to the target audience",
    },

    # --- 模式10：边界模式（Boundary Pattern）---
    # 【用途】严格限定模型只处理特定范围的请求，超出范围直接拒绝。
    # 【原理】比护栏模式更"硬"——超出范围时不是"软拒绝"，而是给出固定的拒绝话术。
    #         适用于需要严格合规的场景（如医疗、法律）。
    "boundary": {
        "name": "Boundary Pattern",
        "template": (
            "You are an assistant that ONLY handles {scope}.\n\n"
            "If the user's request is within scope, help them fully.\n"
            "If the user's request is outside scope, respond exactly with:\n"
            "'{refusal_message}'\n\n"
            "Do not attempt to answer out-of-scope questions.\n\n"
            "User: {user_input}"
        ),
        "variables": ["scope", "refusal_message", "user_input"],
        "temperature": 0.0,  # 拒绝回复需要完全确定性
        "description": "Hard boundary on what the model will and will not respond to",
    },
}


# =============================================================================
# 第二部分：模型配置（Model Configurations）
# =============================================================================
# 【什么是"上下文窗口"（context_window）？】
# 模型能"看到"的总token数（输入+输出）。
# 1个token约等于0.75个英文单词，或1-2个中文字符。
# 上下文窗口越大，能塞入的背景信息越多，但处理也越慢、越贵。
#
# 【什么是 max_tokens？】
# 模型生成回答的最大token数。设太小回答会被截断，设太大浪费钱。

MODEL_CONFIGS = {
    "gpt-4o": {
        "provider": "openai",          # 提供商：OpenAI
        "model": "gpt-4o",             # 模型名称
        "max_tokens": 2048,            # 最大输出token数
        "context_window": 128_000,     # 上下文窗口：128K tokens
    },
    "claude-3.5-sonnet": {
        "provider": "anthropic",       # 提供商：Anthropic
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 2048,
        "context_window": 200_000,     # 上下文窗口：200K tokens
    },
    "gemini-1.5-pro": {
        "provider": "google",          # 提供商：Google
        "model": "gemini-1.5-pro",
        "max_tokens": 2048,
        "context_window": 2_000_000,   # 上下文窗口：2M tokens（非常大！）
    },
}


# =============================================================================
# 第三部分：提示词构建器（Prompt Builder）
# =============================================================================
# 【build_prompt 做了什么？】
# 1. 根据模式名称找到对应的模板
# 2. 检查是否提供了所有需要的变量
# 3. 把变量填入模板，生成最终的提示词文本
# 4. 返回一个包含系统消息、用户消息、温度等信息的字典
#
# 【返回值结构】
# {
#   "system":    系统消息（设定AI的角色和规则），
#   "user":      用户消息（实际的任务指令），
#   "temperature": 温度参数，
#   "pattern":   使用的模式名称，
#   "metadata":  元数据（描述信息、使用的变量等）
# }

def build_prompt(pattern_name, variables, system_override=None):
    """
    根据模式名称和变量，构建完整的提示词。

    参数:
        pattern_name (str): 模式名称，如 "persona", "few_shot" 等
        variables (dict): 模板变量，如 {"role": "医生", "task": "解释感冒"}
        system_override (str, 可选): 自定义系统消息，不传则使用默认值

    返回:
        dict: 包含 system, user, temperature, pattern, metadata 的字典

    示例:
        >>> prompt = build_prompt("persona", {
        ...     "role": "资深Python开发者",
        ...     "experience": "10年经验",
        ...     "style": "简洁直接",
        ...     "priority": "代码质量",
        ...     "task": "解释什么是装饰器"
        ... })
        >>> print(prompt["user"])  # 查看生成的用户消息
    """
    # 第1步：从模式库中查找模式
    pattern = PROMPT_PATTERNS.get(pattern_name)
    if not pattern:
        raise ValueError(f"未知模式: {pattern_name}。可用模式: {list(PROMPT_PATTERNS.keys())}")

    # 第2步：检查是否缺少必要的变量
    # 比如 persona 模式需要 role, experience, style, priority, task 这5个变量
    missing = [v for v in pattern["variables"] if v not in variables]
    if missing:
        raise ValueError(f"模式 {pattern_name} 缺少变量: {missing}")

    # 第3步：用 Python 的 str.format() 方法把变量填入模板
    # 例如 "You are {role}" -> "You are 资深Python开发者"
    rendered = pattern["template"].format(**variables)

    # 第4步：设置系统消息（如果没提供自定义的，就用默认的）
    # 系统消息告诉模型"你是谁"和"你该怎么做"
    system = system_override or f"You are an AI assistant using the {pattern['name']}."

    # 第5步：组装并返回完整的提示词对象
    return {
        "system": system,
        "user": rendered,
        "temperature": pattern["temperature"],
        "pattern": pattern_name,
        "metadata": {
            "description": pattern["description"],
            "variables_used": list(variables.keys()),
        },
    }


# 【build_multi_turn 做了什么？】
# 构建多轮对话的消息列表。与 build_prompt 不同的是，
# 它支持多条消息（用户说→AI说→用户说→AI说...），适合对话场景。
#
# 参数:
#   pattern_name: 模式名称（用来获取推荐温度）
#   turns: 对话轮次列表，每个元素是 (角色, 内容) 的元组
#          角色可以是 "user" 或 "assistant"
#   system_override: 自定义系统消息
#
# 返回:
#   {
#     "messages": [  # 消息列表，按OpenAI格式
#       {"role": "system", "content": "..."},
#       {"role": "user", "content": "..."},
#       {"role": "assistant", "content": "..."},
#       ...
#     ],
#     "temperature": ...,
#     "pattern": ...
#   }

def build_multi_turn(pattern_name, turns, system_override=None):
    pattern = PROMPT_PATTERNS.get(pattern_name)
    if not pattern:
        raise ValueError(f"未知模式: {pattern_name}")

    system = system_override or f"You are an AI assistant using the {pattern['name']}."

    # 构建消息列表：先放系统消息，再放对话轮次
    messages = [{"role": "system", "content": system}]
    for role, content in turns:
        messages.append({"role": role, "content": content})

    return {
        "messages": messages,
        "temperature": pattern["temperature"],
        "pattern": pattern_name,
    }


# =============================================================================
# 第四部分：多模型请求格式化器（Multi-Provider Request Formatters）
# =============================================================================
# 【为什么需要格式化器？】
# 不同的AI提供商（OpenAI、Anthropic、Google）的API格式不同：
#   - OpenAI:    系统消息放在 messages 数组里
#   - Anthropic: 系统消息是单独的 "system" 字段
#   - Google:    系统消息和用户消息合并到 contents 里
#
# 格式化器的作用：把统一的提示词对象，转换为各提供商要求的请求格式。
# 这就是"适配器模式"（Adapter Pattern）的应用。

def format_openai_request(prompt):
    """
    将提示词转换为 OpenAI API 的请求格式。
    OpenAI 的特点是：系统消息和用户消息都在 messages 数组里，
    通过 role 字段区分。
    """
    return {
        "model": MODEL_CONFIGS["gpt-4o"]["model"],
        "messages": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ],
        "temperature": prompt["temperature"],
        "max_tokens": MODEL_CONFIGS["gpt-4o"]["max_tokens"],
    }


def format_anthropic_request(prompt):
    """
    将提示词转换为 Anthropic (Claude) API 的请求格式。
    Anthropic 的特点是：系统消息是顶层的 "system" 字段，
    不在 messages 数组里。这是与 OpenAI 的主要区别。
    """
    return {
        "model": MODEL_CONFIGS["claude-3.5-sonnet"]["model"],
        "system": prompt["system"],  # Anthropic 的系统消息是单独的字段
        "messages": [
            {"role": "user", "content": prompt["user"]},
        ],
        "temperature": prompt["temperature"],
        "max_tokens": MODEL_CONFIGS["claude-3.5-sonnet"]["max_tokens"],
    }


def format_google_request(prompt):
    """
    将提示词转换为 Google Gemini API 的请求格式。
    Google 的格式与前两者差异最大：
    - 用 "contents" 代替 "messages"
    - 用 "parts" 数组来携带文本
    - 用 "generationConfig" 来设置生成参数
    - 系统消息需要合并到用户消息中（Gemini不直接支持单独的系统消息）
    """
    return {
        "model": MODEL_CONFIGS["gemini-1.5-pro"]["model"],
        "contents": [
            {"role": "user", "parts": [{"text": f"{prompt['system']}\n\n{prompt['user']}"}]},
        ],
        "generationConfig": {
            "temperature": prompt["temperature"],
            "maxOutputTokens": MODEL_CONFIGS["gemini-1.5-pro"]["max_tokens"],
        },
    }


# 格式化器注册表：通过提供商名称找到对应的格式化函数
# 这是策略模式（Strategy Pattern）的应用——根据不同的提供商选择不同的策略
FORMATTERS = {
    "openai": format_openai_request,
    "anthropic": format_anthropic_request,
    "google": format_google_request,
}


# =============================================================================
# 第五部分：模拟LLM调用（Simulated LLM Call）
# =============================================================================
# 【为什么要模拟？】
# 真实调用API需要花钱、需要网络、需要API密钥。
# 模拟调用可以让我们在没有API的情况下测试代码逻辑。
# 在实际项目中，你只需要把 simulate_llm_call 替换为真实的HTTP请求即可。
#
# 【MD5哈希的作用】
# 用请求内容生成一个短的"指纹"（前8位），这样不同的请求会产生不同的
# 模拟回复，方便我们区分和调试。
#
# 【返回值说明】
# {
#   "response":      模型的回答文本,
#   "tokens_used":   token用量（prompt=输入token, completion=输出token, total=总计）,
#   "latency_ms":    模拟的API延迟（毫秒）,
#   "finish_reason": 结束原因（"stop"=正常结束, "length"=达到token上限被截断）
# }

def simulate_llm_call(model_name, request):
    time.sleep(0.01)  # 模拟一小段网络延迟

    # 用请求内容的MD5哈希的前8位作为"指纹"
    # 这样不同的请求会得到不同的模拟回复
    prompt_hash = hashlib.md5(json.dumps(request, sort_keys=True).encode()).hexdigest()[:8]

    # 为每个模型准备模拟回复
    # 在真实项目中，这里会是实际的HTTP请求
    simulated_responses = {
        "gpt-4o": {
            "response": (
                f"[GPT-4o response {prompt_hash}] This is a simulated response. "
                "GPT-4o tends to be thorough and well-structured with strong instruction following."
            ),
            "tokens_used": {"prompt": 150, "completion": 45, "total": 195},
            "latency_ms": 850,      # GPT-4o 响应较快
            "finish_reason": "stop",
        },
        "claude-3.5-sonnet": {
            "response": (
                f"[Claude 3.5 Sonnet response {prompt_hash}] This is a simulated response. "
                "Claude tends to be direct, precise, and follows system instructions closely."
            ),
            "tokens_used": {"prompt": 145, "completion": 40, "total": 185},
            "latency_ms": 720,      # Claude 响应最快
            "finish_reason": "end_turn",  # Anthropic用 "end_turn" 表示正常结束
        },
        "gemini-1.5-pro": {
            "response": (
                f"[Gemini 1.5 Pro response {prompt_hash}] This is a simulated response. "
                "Gemini tends to be comprehensive with strong factual grounding."
            ),
            "tokens_used": {"prompt": 155, "completion": 42, "total": 197},
            "latency_ms": 900,      # Gemini 响应稍慢
            "finish_reason": "STOP",  # Google用 "STOP" 表示正常结束
        },
    }

    return simulated_responses.get(
        model_name,
        {"response": "Unknown model", "tokens_used": {}, "latency_ms": 0},
    )


# =============================================================================
# 第六部分：多模型测试运行器（Multi-Model Test Runner）
# =============================================================================
# 【run_prompt_test 做了什么？】
# 把同一个提示词发送到多个模型，收集每个模型的：
#   - 回答文本
#   - token用量（花费多少）
#   - 响应延迟（多快）
#   - 结束原因（正常结束还是被截断）
#
# 这就是"A/B测试"的思想——用同一个输入比较不同模型的表现。

def run_prompt_test(prompt, models=None):
    """
    对指定的模型列表运行提示词测试。

    参数:
        prompt (dict): 由 build_prompt() 生成的提示词对象
        models (list, 可选): 要测试的模型名称列表，默认测试所有模型

    返回:
        dict: {模型名: 测试结果} 的字典
    """
    if models is None:
        models = list(MODEL_CONFIGS.keys())

    results = {}
    for model_name in models:
        # 第1步：获取模型配置和对应的格式化器
        config = MODEL_CONFIGS[model_name]
        formatter = FORMATTERS[config["provider"]]

        # 第2步：将提示词转换为该提供商的API请求格式
        request = formatter(prompt)

        # 第3步：调用（模拟的）LLM并记录耗时
        start = time.time()
        response = simulate_llm_call(model_name, request)
        wall_time = (time.time() - start) * 1000  # 转换为毫秒

        # 第4步：保存测试结果
        results[model_name] = {
            "response": response["response"],
            "tokens": response["tokens_used"],
            "api_latency_ms": response["latency_ms"],
            "wall_time_ms": round(wall_time, 1),
            "finish_reason": response.get("finish_reason"),
            "request_payload": request,  # 保存请求内容，方便调试
        }

    return results


# =============================================================================
# 第七部分：回答评分器（Response Scorer）
# =============================================================================
# 【评分标准说明】
# 评分器根据预设的标准（criteria）给模型回答打分。支持4种评分维度：
#
# 1. max_words（最大字数）- 回答是否在字数限制内
#    例如: max_words=200 表示回答不能超过200个单词
#
# 2. required_keywords（必要关键词）- 回答是否包含指定的关键词
#    例如: required_keywords=["rate limit", "API"] 要求回答中必须出现这两个词
#    评分 = 找到的关键词数 / 总关键词数（覆盖率）
#
# 3. forbidden_phrases（禁止短语）- 回答中不能出现的词
#    例如: forbidden_phrases=["in conclusion"] 要求回答中不能出现这些套话
#
# 4. expected_format（期望格式）- 回答是否符合指定格式
#    支持: "json", "bullet_points"（要点列表）, "numbered_list"（编号列表）
#
# 【综合评分（composite_score）】
# 把所有评分明细中的布尔值（True/False）和0-1之间的浮点数取平均值。
# 最终得分范围：0.0（最差）到 1.0（完美）

def score_response(response_text, criteria):
    """
    根据评分标准对模型回答进行评分。

    参数:
        response_text (str): 模型的回答文本
        criteria (dict): 评分标准，包含 max_words, required_keywords, forbidden_phrases, expected_format

    返回:
        dict: 评分结果，包含各项评分明细和 composite_score（综合得分）
    """
    scores = {}

    # --- 评分维度1：字数检查 ---
    if "max_words" in criteria:
        word_count = len(response_text.split())
        scores["word_count"] = word_count
        scores["length_compliant"] = word_count <= criteria["max_words"]

    # --- 评分维度2：关键词覆盖率 ---
    if "required_keywords" in criteria:
        # 遍历所有必要关键词，检查是否出现在回答中（不区分大小写）
        found = [kw for kw in criteria["required_keywords"] if kw.lower() in response_text.lower()]
        scores["keywords_found"] = found
        # 计算覆盖率：找到的关键词数 / 总关键词数
        scores["keyword_coverage"] = (
            len(found) / len(criteria["required_keywords"])
            if criteria["required_keywords"]
            else 1.0  # 如果没有要求关键词，覆盖率视为100%
        )

    # --- 评分维度3：禁止短语检查 ---
    if "forbidden_phrases" in criteria:
        violations = [fp for fp in criteria["forbidden_phrases"] if fp.lower() in response_text.lower()]
        scores["forbidden_violations"] = violations
        scores["no_violations"] = len(violations) == 0  # True=没有违规

    # --- 评分维度4：格式检查 ---
    if "expected_format" in criteria:
        fmt = criteria["expected_format"]

        if fmt == "json":
            # 尝试解析为JSON，成功则格式正确
            try:
                json.loads(response_text)
                scores["format_valid"] = True
            except (json.JSONDecodeError, TypeError):
                scores["format_valid"] = False

        elif fmt == "bullet_points":
            # 检查是否至少一半的非空行是以 "- * 1" 开头的列表项
            lines = [line.strip() for line in response_text.split("\n") if line.strip()]
            bullet_lines = [line for line in lines if line.startswith(("-", "*", "1"))]
            scores["format_valid"] = len(bullet_lines) >= len(lines) * 0.5

        elif fmt == "numbered_list":
            # 用正则表达式检查是否有至少2行以数字开头（如 "1. xxx", "2. xxx"）
            numbered = re.findall(r"^\d+\.", response_text, re.MULTILINE)
            scores["format_valid"] = len(numbered) >= 2

        else:
            scores["format_valid"] = True  # 未知格式默认通过

    # --- 计算综合评分 ---
    # 遍历所有评分明细，找出布尔值和0-1之间的浮点数，取平均
    total = 0
    count = 0
    for key, value in scores.items():
        if isinstance(value, bool):
            # 布尔值：True算1分，False算0分
            total += 1.0 if value else 0.0
            count += 1
        elif isinstance(value, float) and 0 <= value <= 1:
            # 0-1之间的浮点数直接加入（如 keyword_coverage）
            total += value
            count += 1

    scores["composite_score"] = round(total / count, 3) if count > 0 else 0.0
    return scores


# =============================================================================
# 第八部分：模型比较器（Model Comparator）
# =============================================================================
# 【compare_models 做了什么？】
# 1. 对每个模型的回答进行评分
# 2. 按综合得分从高到低排序
# 3. 返回比较结果和排名

def compare_models(test_results, criteria):
    """
    比较多个模型在同一测试上的表现。

    参数:
        test_results (dict): run_prompt_test() 的返回值
        criteria (dict): 评分标准

    返回:
        tuple: (比较详情字典, 排名列表)
    """
    comparison = {}
    for model_name, result in test_results.items():
        scores = score_response(result["response"], criteria)
        comparison[model_name] = {
            "scores": scores,
            "tokens": result["tokens"],
            "latency_ms": result["api_latency_ms"],
        }

    # 按综合得分降序排序（得分最高的排在前面）
    ranked = sorted(
        comparison.items(),
        key=lambda x: x[1]["scores"]["composite_score"],
        reverse=True,
    )
    return comparison, ranked


# =============================================================================
# 第九部分：测试套件（Test Suite）
# =============================================================================
# 【什么是测试套件？】
# 一组预先定义好的测试用例，每个用例包含：
#   - name:      测试名称
#   - pattern:   使用的提示词模式
#   - variables: 模板变量（实际的任务内容）
#   - criteria:  评分标准
#
# 这些测试用例覆盖了不同的提示词模式和场景，
# 帮助我们理解每种模式的效果。

TEST_SUITE = [
    # 测试1：角色模式 - 技术写作
    # 场景：让模型扮演Stripe的资深技术作家，解释API限速
    {
        "name": "Persona: Technical Writer",
        "pattern": "persona",
        "variables": {
            "role": "a senior technical writer at Stripe",
            "experience": "10 years of API documentation experience",
            "style": "precise, concise, and example-driven",
            "priority": "clarity over comprehensiveness",
            "task": "Explain what an API rate limit is and why it exists.",
        },
        "criteria": {
            "max_words": 200,  # 回答不超过200词
            "required_keywords": ["rate limit", "API", "requests"],  # 必须包含这些关键词
            "forbidden_phrases": ["in conclusion", "it is important to note"],  # 不能出现这些套话
        },
    },

    # 测试2：少样本模式 - 情感分析
    # 场景：给2个情感分析的例子，让模型分析第3条评论
    {
        "name": "Few-Shot: Sentiment Analysis",
        "pattern": "few_shot",
        "variables": {
            "examples": (
                'Input: "The food was amazing but service was slow"\n'
                'Output: {"sentiment": "mixed", "food": "positive", "service": "negative"}\n\n'
                'Input: "Terrible experience, never coming back"\n'
                'Output: {"sentiment": "negative", "food": null, "service": "negative"}'
            ),
            "input": "Great ambiance and the pasta was perfect, though a bit pricey",
        },
        "criteria": {
            "expected_format": "json",  # 回答必须是合法的JSON
            "required_keywords": ["sentiment"],
        },
    },

    # 测试3：思维链模式 - 数学问题
    # 场景：让模型逐步推理折扣和优惠券的计算
    {
        "name": "Chain-of-Thought: Math Problem",
        "pattern": "chain_of_thought",
        "variables": {
            "problem": (
                "A store offers 20% off all items. An item originally costs $85. "
                "There is also a $10 coupon. Which saves more: applying the discount "
                "first then the coupon, or the coupon first then the discount?"
            ),
        },
        "criteria": {
            "required_keywords": ["discount", "coupon", "$"],
            "max_words": 300,
        },
    },

    # 测试4：模板填充模式 - 简历信息提取
    # 场景：从一段文本中提取结构化信息
    {
        "name": "Template Fill: Resume Extraction",
        "pattern": "template_fill",
        "variables": {
            "text": (
                "John Smith is a software engineer at Google with 5 years of experience. "
                "He graduated from MIT with a BS in Computer Science in 2019. "
                "He specializes in distributed systems and Go programming."
            ),
            "template_structure": (
                "Name: [full name]\n"
                "Company: [current employer]\n"
                "Years of Experience: [number]\n"
                "Education: [degree, school, year]\n"
                "Specialties: [comma-separated list]"
            ),
        },
        "criteria": {
            "required_keywords": ["John Smith", "Google", "MIT"],
        },
    },

    # 测试5：护栏模式 - 受限的Python辅导助手
    # 场景：模型只能回答Python编程问题，且不能直接给出完整答案
    {
        "name": "Guardrail: Scoped Assistant",
        "pattern": "guardrail",
        "variables": {
            "role": "Python programming tutor",
            "domain": "Python programming",
            "additional_rules": "Do not write complete solutions. Guide the student with hints.",
            "question": "How do I sort a list of dictionaries by a specific key?",
        },
        "criteria": {
            "required_keywords": ["sorted", "key", "lambda"],
            "forbidden_phrases": ["here is the complete solution"],
        },
    },
]


# =============================================================================
# 第十部分：测试套件运行器（Test Suite Runner）
# =============================================================================
# 【run_test_suite 做了什么？】
# 1. 遍历 TEST_SUITE 中的每个测试用例
# 2. 用 build_prompt() 构建提示词
# 3. 用 run_prompt_test() 在所有模型上运行
# 4. 用 compare_models() 比较并排名
# 5. 打印结果表格
# 6. 最后统计哪个模型"赢"得最多

def run_test_suite():
    print("=" * 70)
    print("  PROMPT ENGINEERING TEST SUITE")
    print("=" * 70)

    all_results = []  # 收集所有测试的结果

    for test in TEST_SUITE:
        # 打印测试标题
        print(f"\n{'=' * 60}")
        print(f"  Test: {test['name']}")
        print(f"  Pattern: {test['pattern']}")
        print(f"{'=' * 60}")

        # 构建提示词
        prompt = build_prompt(test["pattern"], test["variables"])
        print(f"\n  System: {prompt['system'][:80]}...")
        print(f"  User prompt: {prompt['user'][:120]}...")
        print(f"  Temperature: {prompt['temperature']}")

        # 在所有模型上运行测试
        results = run_prompt_test(prompt)

        # 比较模型表现并排名
        comparison, ranked = compare_models(results, test["criteria"])

        # 打印排名表格
        print(f"\n  {'Model':<25} {'Score':>8} {'Tokens':>8} {'Latency':>10}")
        print(f"  {'-' * 55}")
        for model_name, data in ranked:
            score = data["scores"]["composite_score"]
            tokens = data["tokens"].get("total", 0)
            latency = data["latency_ms"]
            print(f"  {model_name:<25} {score:>8.3f} {tokens:>8} {latency:>8}ms")

        # 记录本次测试结果
        all_results.append({
            "test": test["name"],
            "pattern": test["pattern"],
            "rankings": [(name, data["scores"]["composite_score"]) for name, data in ranked],
        })

    # --- 打印总结：统计每个模型赢了多少次 ---
    print(f"\n\n{'=' * 70}")
    print("  SUMMARY: MODEL RANKINGS ACROSS ALL TESTS")
    print(f"{'=' * 70}")

    model_wins = {}
    for result in all_results:
        if result["rankings"]:
            winner = result["rankings"][0][0]  # 排名第一的模型
            model_wins[winner] = model_wins.get(winner, 0) + 1

    for model, wins in sorted(model_wins.items(), key=lambda x: x[1], reverse=True):
        print(f"  {model}: {wins} wins out of {len(all_results)} tests")

    return all_results


# =============================================================================
# 第十一部分：演示函数（Demo Functions）
# =============================================================================

def run_pattern_catalog_demo():
    """打印所有可用的提示词模式目录，方便快速查阅。"""
    print("=" * 70)
    print("  PROMPT PATTERN CATALOG")
    print("=" * 70)

    for name, pattern in PROMPT_PATTERNS.items():
        print(f"\n  [{name}] {pattern['name']}")
        print(f"    {pattern['description']}")
        print(f"    Variables: {', '.join(pattern['variables'])}")
        print(f"    Recommended temp: {pattern['temperature']}")


def run_single_prompt_demo():
    """演示如何用 persona 模式构建一个单独的提示词并测试。"""
    print(f"\n{'=' * 70}")
    print("  SINGLE PROMPT BUILD + TEST")
    print("=" * 70)

    # 用 persona 模式构建一个提示词
    # 角色：Netflix的资深DevOps工程师
    # 任务：解释为什么容器编排对微服务很重要
    prompt = build_prompt("persona", {
        "role": "a senior DevOps engineer at Netflix",
        "experience": "8 years of infrastructure automation",
        "style": "direct and practical",
        "priority": "reliability over speed",
        "task": "Explain why container orchestration matters for microservices.",
    })

    # 打印构建结果
    print(f"\n  System message:\n    {prompt['system']}")
    print(f"\n  User message:\n    {prompt['user'][:200]}...")
    print(f"\n  Temperature: {prompt['temperature']}")
    print(f"\n  Pattern metadata: {json.dumps(prompt['metadata'], indent=4)}")

    # 在所有模型上测试
    results = run_prompt_test(prompt)
    for model, result in results.items():
        print(f"\n  [{model}]")
        print(f"    Response: {result['response'][:100]}...")
        print(f"    Tokens: {result['tokens']}")
        print(f"    Latency: {result['api_latency_ms']}ms")


# =============================================================================
# 主程序入口
# =============================================================================
# 【运行顺序】
# 1. 先展示所有可用的提示词模式
# 2. 再演示一个单独的提示词构建和测试
# 3. 最后运行完整的测试套件，比较不同模式在不同模型上的表现
#
# 运行方式: python prompt_engineering.py

if __name__ == "__main__":
    run_pattern_catalog_demo()   # 展示模式目录
    run_single_prompt_demo()     # 单个提示词演示
    run_test_suite()             # 运行测试套件