# =============================================================================
# 高级提示技术：少样本学习 + 思维链 + 自一致性 + 思维树 + ReAct
# 本文件对应课程文档：phases/11-llm-engineering/02-few-shot-cot/docs/zh.md
# 参考来源：
#   - Wei et al. (2022): Chain-of-Thought Prompting (思维链提示)
#   - Wang et al. (2023): Self-Consistency (自一致性)
#   - Yao et al. (2023): Tree of Thoughts (思维树)
#   - Yao et al. (2023): ReAct: Reasoning and Acting (推理与行动)
# =============================================================================
#
# 【初学者导读】
# 这个文件展示了6种提升LLM推理能力的提示技术，从简单到复杂：
#
#   1. Zero-Shot（零样本）     - 直接问问题，不给任何示例
#   2. Zero-Shot CoT（零样本思维链）- 加一句"Let's think step by step"
#   3. Few-Shot CoT（少样本思维链）- 给几个带推理过程的示例
#   4. Self-Consistency（自一致性）- 多次回答，投票选最常见的答案
#   5. Tree of Thoughts（思维树） - 探索多条推理路径，选最好的
#   6. ReAct（推理+行动）        - 让模型在推理时调用工具（如计算器）
#
# 【核心思想】
# LLM不是计算器，它的"推理"是基于模式匹配的。
# 通过精心设计提示词，我们可以引导模型更系统地思考，从而提高准确率。
#
# 【运行方式】
# 需要设置环境变量 OPENAI_API_KEY
# 运行: python advanced_prompting.py
#

import json
import re
import os
from collections import Counter  # 计数器，用于统计投票
from openai import OpenAI  # OpenAI 官方 Python SDK（需要先 pip install openai）


# =============================================================================
# 第一部分：GSM8K 示例数据（Few-Shot Examples）
# =============================================================================
# 【什么是 GSM8K？】
# GSM8K（Grade School Math 8K）是一个包含8500道小学数学应用题的数据集。
# 这里的5个例子是典型的 GSM8K 题目，用于"少样本学习"。
#
# 【每道题包含3个部分】
#   - question:  题目文本
#   - reasoning: 详细的推理过程（思维链）
#   - answer:    最终数字答案
#
# 【为什么推理过程很重要？】
# 给模型看"怎么想"比只看"答案是什么"更有用。
# 这就像老师解题时写步骤，比直接写答案更能教会学生。
#
# 【数据集用法】
# 这些例子会被插入到提示词中，作为模型学习的"范例"。
# 模型会模仿这些例子的推理风格来解答新题目。

GSM8K_EXAMPLES = [
    {
        "question": (
            "Janet's ducks lay 16 eggs per day. She eats three for breakfast "
            "every morning and bakes muffins for her friends every day with four. "
            "She sells every remaining egg at the farmers' market for $2. "
            "How much does she make every day at the farmers' market?"
        ),
        "reasoning": (
            "Janet's ducks lay 16 eggs per day. She eats 3 and bakes with 4, "
            "using 3 + 4 = 7 eggs. So she has 16 - 7 = 9 eggs left. "
            "She sells each for $2, so she makes 9 * 2 = $18 per day."
        ),
        "answer": "18",
    },
    {
        "question": (
            "A robe takes 2 bolts of blue fiber and half that much white fiber. "
            "How many bolts in total does it take?"
        ),
        "reasoning": (
            "It takes 2 bolts of blue fiber. "
            "Half of 2 is 1, so it takes 1 bolt of white fiber. "
            "In total, 2 + 1 = 3 bolts."
        ),
        "answer": "3",
    },
    {
        "question": (
            "Josh decides to try flipping a house. He buys a house for $80,000 "
            "and puts $50,000 in repairs. This increased the value of the house "
            "by 150%. How much profit did he make?"
        ),
        "reasoning": (
            "The house cost $80,000. Repairs cost $50,000. "
            "Total investment: 80,000 + 50,000 = $130,000. "
            "The value increased by 150% of $80,000: 80,000 * 1.5 = $120,000. "
            "New value: 80,000 + 120,000 = $200,000. "
            "Profit: 200,000 - 130,000 = $70,000."
        ),
        "answer": "70000",
    },
    {
        "question": (
            "James writes a 3-page letter to 2 different friends twice a week. "
            "How many pages does he write a year?"
        ),
        "reasoning": (
            "He writes to 2 friends, so 2 letters each time. "
            "Each letter is 3 pages, so 2 * 3 = 6 pages per session. "
            "He does this twice a week: 6 * 2 = 12 pages per week. "
            "In a year (52 weeks): 12 * 52 = 624 pages."
        ),
        "answer": "624",
    },
    {
        "question": (
            "Every day, Wendi feeds each of her chickens three cups of mixed "
            "chicken feed, containing seeds, mealworms, and vegetables. She gives "
            "the chickens their feed in three separate meals. In the morning, she "
            "gives her flock of chickens 15 cups of feed. In the afternoon, she "
            "gives her chickens another 25 cups of feed. How many cups of feed "
            "does she need to give her chickens in the final meal of the day if "
            "the carry-over from prior feedings was 35 cups?"
        ),
        "reasoning": (
            "Morning feed: 15 cups. Afternoon feed: 25 cups. "
            "Total so far: 15 + 25 = 40 cups. "
            "Carry-over: 35 cups. Effective fed: 40 - 35 = 5 cups net new. "
            "Wait, let me re-read. She has a flock. Morning: 15 cups. Afternoon: 25 cups. "
            "Total given so far: 15 + 25 = 40 cups. "
            "With 35 cups carry-over, total available is 40 + 35 = 75 cups. "
            "Actually, carry-over means leftover from before. "
            "Each chicken gets 3 cups/day. Number of chickens: 15/? "
            "Morning she gives 15 cups. Each meal is 1/3 of daily feed. "
            "So 15 cups in morning = 1/3 of total daily. Total daily = 45 cups. "
            "She gave 15 + 25 = 40 cups in first two meals. "
            "Remaining: 45 - 40 = 5 cups. But carry-over is 35 cups. "
            "She needs 5 - 35 = needs to give negative? No. "
            "Total needed for last meal: the daily total minus what was already fed. "
            "15 chickens (since 15 cups / 1 cup per chicken per meal = 15 chickens). "
            "Daily total: 15 * 3 = 45 cups. Given: 15 + 25 = 40. "
            "Last meal needs: 45 - 40 = 5 cups. But the carry-over is extra, not a reduction. "
            "She needs to give 45 - 40 + 35 = 40 cups. Wait. "
            "Hmm, with 35 cups carry-over from prior feedings already counted: "
            "She needs to provide 45 - 35 = 10 total new cups today. "
            "She already gave 15 + 25 = 40. That's way more than 10. "
            "The question asks how many cups in the final meal. "
            "Let me just compute: total daily = 15 * 3 = 45. "
            "Already given: 15 + 25 = 40. Last meal: 45 - 40 = 5."
        ),
        "answer": "5",
    },
]


# =============================================================================
# 第二部分：答案提取器（Answer Extractor）
# =============================================================================
# 【为什么要提取答案？】
# 模型的回答通常是一段完整的推理过程，最终答案嵌在文字中。
# 我们需要从文本中"提取"出最终的数字答案，才能自动判断对错。
#
# 【提取策略（按优先级）】
# 1. 匹配 "The answer is 42" 或 "The answer is: 42" 这种明确格式
# 2. 匹配 "#### 42" 这种 GSM8K 标准格式
# 3. 匹配 "= 42" 这种等式结尾格式
# 4. 以上都不匹配时，取文本中最后一个数字
#
# 【正则表达式说明】
# r"..." 是原始字符串，反斜杠不会被转义
# [Tt]he: 匹配 The 或 the
# \$?: 可选的美元符号
# [\d,]+\.?\d*: 匹配数字，如 "1,234.56" 或 "42"

def extract_answer(text):
    """从模型回答中提取数字答案。

    参数:
        text (str): 模型的完整回答文本

    返回:
        str 或 None: 提取到的数字字符串，如 "42"；未找到则返回 None
    """
    if not text:
        return None

    # 按优先级尝试不同的正则模式
    patterns = [
        r"[Tt]he answer is[:\s]*\$?([\d,]+\.?\d*)",  # "The answer is 42"
        r"[Tt]he answer is[:\s]*([\d,]+\.?\d*)",       # 备选模式
        r"#### ([\d,]+\.?\d*)",                         # "#### 42"（GSM8K格式）
        r"= \$?([\d,]+\.?\d*)\s*$",                     # "= 42"（等式结尾）
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).replace(",", "")  # 去掉千位分隔符

    # 兜底：取文本中最后一个数字
    numbers = re.findall(r"[\d,]+\.?\d*", text)
    if numbers:
        return numbers[-1].replace(",", "")
    return None


# =============================================================================
# 第三部分：提示词构建器（Prompt Builders）
# =============================================================================
# 【三种提示词构建方式的区别】
#
# build_zero_shot_prompt()     - 零样本：只给问题，不给示例
# build_zero_shot_cot_prompt() - 零样本思维链：加一句"Let's think step by step"
# build_cot_prompt()           - 少样本思维链：给几个带推理过程的例子
#
# 【为什么 "Let's think step by step" 有效？】
# 这句话看似简单，但它触发了模型的"逐步推理"模式。
# 研究表明，仅加这一句话就能显著提高数学推理准确率。
# 这就是"零样本思维链"（Zero-Shot CoT）的魔力。

def build_cot_prompt(question, examples, num_examples=3):
    """构建少样本思维链提示词。

    工作原理：
    1. 设置系统消息，要求模型展示推理过程
    2. 将示例按 "Q: ... A: ... The answer is ..." 格式拼接
    3. 在末尾加上新问题

    参数:
        question (str): 要解答的数学问题
        examples (list): 示例列表，每个包含 question, reasoning, answer
        num_examples (int): 使用多少个示例（默认3个）

    返回:
        tuple: (系统消息, 用户消息)
    """
    system = (
        "You are a precise math problem solver. "
        "For each problem, show your step-by-step reasoning clearly. "
        "After your reasoning, state your final answer on the last line "
        "in exactly this format: 'The answer is [number]'."
    )

    # 拼接示例：每个示例都是 "Q: 题目 A: 推理过程 The answer is 答案"
    example_text = ""
    for ex in examples[:num_examples]:
        example_text += f"Q: {ex['question']}\n"
        example_text += f"A: {ex['reasoning']} The answer is {ex['answer']}.\n\n"

    # 在示例后面加上新问题，等模型续写
    user = f"{example_text}Q: {question}\nA:"
    return system, user


def build_zero_shot_cot_prompt(question):
    """构建零样本思维链提示词。

    【关键魔法】只加一句 "Let's think step by step" 就能激活模型的逐步推理能力。
    这比零样本好很多，比完整的少样本简单得多。

    参数:
        question (str): 要解答的数学问题

    返回:
        tuple: (系统消息, 用户消息)
    """
    system = (
        "You are a precise math problem solver. "
        "Show your step-by-step reasoning. "
        "End with: 'The answer is [number]'."
    )
    # "Let's think step by step" 是零样本思维链的触发词
    user = f"Q: {question}\nA: Let's think step by step."
    return system, user


def build_zero_shot_prompt(question):
    """构建零样本提示词（无推理过程，只要最终答案）。

    【用途】作为基线对比——看看不加任何技巧时模型的表现。
    通常准确率最低，但速度最快。

    参数:
        question (str): 要解答的数学问题

    返回:
        tuple: (系统消息, 用户消息)
    """
    system = (
        "You are a precise math problem solver. "
        "Give only the final numerical answer. "
        "End with: 'The answer is [number]'."
    )
    user = f"Q: {question}\nA:"
    return system, user


# =============================================================================
# 第四部分：LLM 调用封装（LLM Call Wrapper）
# =============================================================================
# 【call_llm 做了什么？】
# 封装了 OpenAI API 的调用，统一处理：
#   - 系统消息（system）：设定AI的角色
#   - 用户消息（user）：实际的问题
#   - temperature：控制随机性（0=最确定，1=最随机）
#   - max_tokens：最大输出长度
#
# 【为什么用 temperature=0？】
# 对于数学推理，我们希望结果是确定性的（每次得到相同答案）。
# temperature=0 意味着模型总是选择概率最高的词。

def call_llm(client, model, system, user, temperature=0.0):
    """调用 OpenAI API 获取模型回答。

    参数:
        client: OpenAI 客户端实例
        model (str): 模型名称，如 "gpt-4o"
        system (str): 系统消息
        user (str): 用户消息
        temperature (float): 温度参数，0=确定性，1=创造性

    返回:
        str: 模型的回答文本
    """
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=1024,
    )
    return response.choices[0].message.content


# =============================================================================
# 第五部分：三种基础求解方法
# =============================================================================

def zero_shot_solve(question, client, model):
    """零样本求解：直接问问题，不给任何示例。

    【流程】问题 → 模型 → 答案
    【特点】最简单，但准确率通常最低。
    """
    system, user = build_zero_shot_prompt(question)
    text = call_llm(client, model, system, user, temperature=0.0)
    return extract_answer(text), text


def zero_shot_cot_solve(question, client, model):
    """零样本思维链求解：加一句"Let's think step by step"。

    【流程】问题 + "让我们一步步思考" → 模型推理 → 答案
    【特点】比零样本好很多，几乎不需要额外工作。
    """
    system, user = build_zero_shot_cot_prompt(question)
    text = call_llm(client, model, system, user, temperature=0.0)
    return extract_answer(text), text


def few_shot_cot_solve(question, examples, client, model, num_examples=3):
    """少样本思维链求解：给几个带推理过程的示例。

    【流程】示例（题目+推理+答案）+ 新问题 → 模型模仿推理 → 答案
    【特点】准确率最高，但需要准备好的示例。
    """
    system, user = build_cot_prompt(question, examples, num_examples)
    text = call_llm(client, model, system, user, temperature=0.0)
    return extract_answer(text), text


# =============================================================================
# 第六部分：自一致性（Self-Consistency）
# =============================================================================
# 【什么是自一致性？】
# 核心思想：如果一个问题的答案是正确的，那么从不同角度推理应该得到相同答案。
#
# 【工作原理】
# 1. 用 temperature>0 让模型生成多个不同的推理过程（n_samples次）
# 2. 从每个推理过程中提取答案
# 3. 用"投票"选出出现最多的答案
#
# 【为什么有效？】
# - 正确的推理路径通常会汇聚到同一个答案
# - 错误的推理路径会分散到不同的错误答案
# - 所以"多数票"往往是正确答案
#
# 【与直接生成的区别】
# 直接生成（temperature=0）只走一条路，可能走错。
# 自一致性走多条路，然后投票，大大降低走错路的概率。

def self_consistency_solve(question, examples, client, model, n_samples=5):
    """用自一致性方法求解。

    参数:
        question (str): 数学问题
        examples (list): 示例列表
        client: OpenAI 客户端
        model (str): 模型名称
        n_samples (int): 采样次数（默认5次，越多越可靠，但越贵）

    返回:
        tuple: (最佳答案, 置信度, 所有推理过程, 投票统计)
    """
    system, user = build_cot_prompt(question, examples)

    answers = []     # 收集所有提取到的答案
    reasonings = []  # 收集所有推理过程

    # 多次采样：用 temperature=0.7 让每次生成不同的推理路径
    for _ in range(n_samples):
        text = call_llm(client, model, system, user, temperature=0.7)
        reasonings.append(text)
        answer = extract_answer(text)
        if answer is not None:
            answers.append(answer)

    if not answers:
        return None, 0.0, reasonings, Counter()

    # 投票统计：用 Counter 统计每个答案出现的次数
    vote_counts = Counter(answers)
    # 选出票数最高的答案
    best_answer = vote_counts.most_common(1)[0][0]
    # 计算置信度：最高票数 / 总票数
    confidence = vote_counts[best_answer] / len(answers)

    return best_answer, confidence, reasonings, vote_counts


# =============================================================================
# 第七部分：思维树（Tree of Thoughts）
# =============================================================================
# 【什么是思维树？】
# 思维树是一种更高级的推理策略，模拟人类"探索多条思路"的过程。
#
# 【工作原理（类比）】
# 想象你在解一道难题：
# 1. 先想出3种不同的解题思路（广度优先）
# 2. 评估每条思路的可行性（打分）
# 3. 选最好的2条思路继续深入（剪枝）
# 4. 对每条思路再想出2种延伸方向
# 5. 再评估、再选择、再深入...
# 6. 最终选得分最高的完整推理路径
#
# 【与自一致性的区别】
# - 自一致性：独立生成多个答案，最后投票（平行搜索）
# - 思维树：逐步探索和评估，动态选择最佳路径（树搜索）
#
# 【参数说明】
# - breadth（广度）：每个节点生成多少个候选思路
# - depth（深度）：探索多少层（每层代表推理的一步）

def generate_initial_thoughts(question, client, model, breadth=3):
    """生成初始的解题思路（思维树的第一层）。

    参数:
        question (str): 数学问题
        client: OpenAI 客户端
        model (str): 模型名称
        breadth (int): 生成多少条不同的思路

    返回:
        list: 多条思路的文本列表
    """
    system = (
        "You are a math problem solver exploring different solution approaches. "
        "Generate one distinct approach to solving this problem. "
        "Show your partial reasoning. Do not give the final answer yet."
    )
    thoughts = []
    for i in range(breadth):
        user = (
            f"Problem: {question}\n\n"
            f"Generate approach #{i + 1} (use a different strategy than previous approaches). "
            f"Think about: arithmetic breakdown, working backwards, estimation, "
            f"or algebraic formulation."
        )
        text = call_llm(client, model, system, user, temperature=0.9)
        thoughts.append(text)
    return thoughts


def evaluate_thought(thought, question, client, model):
    """评估一条思路的质量（打分0.0-1.0）。

    【评估维度】
    - 算术正确性：计算步骤有没有错
    - 逻辑连贯性：推理逻辑是否通顺
    - 进展程度：离最终答案还有多远

    参数:
        thought (str): 要评估的思路文本
        question (str): 原始问题
        client: OpenAI 客户端
        model (str): 模型名称

    返回:
        float: 0.0（最差）到 1.0（最好）的分数
    """
    system = (
        "You are a math reasoning evaluator. "
        "Score the following partial reasoning on a scale from 0.0 to 1.0. "
        "Consider: correctness of arithmetic, logical coherence, "
        "progress toward the answer. "
        "Respond with ONLY a number between 0.0 and 1.0."
    )
    user = f"Problem: {question}\n\nReasoning so far:\n{thought}\n\nScore:"
    text = call_llm(client, model, system, user, temperature=0.0)
    try:
        # 从回答中提取数字分数
        score = float(re.search(r"([\d.]+)", text).group(1))
        # 限制在 0.0-1.0 范围内
        return min(max(score, 0.0), 1.0)
    except (AttributeError, ValueError):
        return 0.5  # 解析失败时给中间分


def extend_thought(thought, question, client, model, breadth=2):
    """延伸一条思路，生成多个可能的后续推理。

    参数:
        thought (str): 当前的推理过程
        question (str): 原始问题
        client: OpenAI 客户端
        model (str): 模型名称
        breadth (int): 生成多少个延伸方向

    返回:
        list: 多个延伸后的完整推理文本
    """
    system = (
        "You are a math problem solver continuing a line of reasoning. "
        "Take the partial reasoning below and extend it further toward a solution. "
        "Show your continued reasoning. If you reach the final answer, "
        "state it as: 'The answer is [number]'."
    )
    extensions = []
    for i in range(breadth):
        user = (
            f"Problem: {question}\n\n"
            f"Reasoning so far:\n{thought}\n\n"
            f"Continue this reasoning (approach #{i + 1}):"
        )
        text = call_llm(client, model, system, user, temperature=0.8)
        # 将原始思路和延伸拼接在一起
        extensions.append(f"{thought}\n\n{text}")
    return extensions


def tree_of_thought_solve(question, client, model, breadth=3, depth=3):
    """用思维树方法求解。

    【算法流程】
    1. 生成 breadth 条初始思路
    2. 对每条思路打分
    3. 选得分最高的 top_k 条继续探索
    4. 对每条思路生成 breadth 个延伸
    5. 对每个延伸打分
    6. 重复 depth 次
    7. 返回得分最高的完整推理路径中的答案

    参数:
        question (str): 数学问题
        client: OpenAI 客户端
        model (str): 模型名称
        breadth (int): 每层生成的候选数
        depth (int): 探索深度

    返回:
        tuple: (答案, 最佳推理路径)
    """
    # 第1步：生成初始思路
    thoughts = generate_initial_thoughts(question, client, model, breadth)

    # 第2步：对每条思路打分并排序
    scored = [(t, evaluate_thought(t, question, client, model)) for t in thoughts]
    scored.sort(key=lambda x: x[1], reverse=True)  # 按分数降序排列

    # 第3步：逐层深入探索
    for current_depth in range(1, depth):
        next_thoughts = []
        top_k = min(2, len(scored))  # 取前2条最优思路继续探索

        for thought, score in scored[:top_k]:
            # 延伸当前思路
            extensions = extend_thought(thought, question, client, model, breadth)
            # 对每个延伸打分
            for ext in extensions:
                ext_score = evaluate_thought(ext, question, client, model)
                next_thoughts.append((ext, ext_score))

        if next_thoughts:
            # 更新为新的候选思路
            scored = sorted(next_thoughts, key=lambda x: x[1], reverse=True)

    # 返回得分最高的思路
    best_thought = scored[0][0] if scored else ""
    return extract_answer(best_thought), best_thought


# =============================================================================
# 第八部分：ReAct（Reasoning + Acting）
# =============================================================================
# 【什么是 ReAct？】
# ReAct = Reasoning（推理）+ Acting（行动）
#
# 核心思想：让模型在推理过程中可以"调用工具"（如计算器）。
#
# 【工作流程（类比）】
# 想象你是一个解题的学生，旁边有一个计算器：
# 1. 你想："这道题需要算 85 * 0.8"（Thought）
# 2. 你按下计算器："85 * 0.8 = 68"（Action → Observation）
# 3. 你继续想："然后减去10..."（Thought）
# 4. 你再按计算器："68 - 10 = 58"（Action → Observation）
# 5. 你得出结论："答案是58"（Answer）
#
# 【为什么比纯推理更好？】
# LLM 不擅长精确计算，但擅长推理。
# ReAct 让 LLM 负责推理，计算器负责计算，各取所长。
#
# 【三种输出格式】
# - Thought: [推理内容]  → 继续思考
# - Action: calculate [表达式]  → 调用计算器
# - Answer: [最终数字]  → 给出答案

def react_solve(question, client, model, max_steps=5):
    """用 ReAct 方法求解（推理 + 计算器工具）。

    参数:
        question (str): 数学问题
        client: OpenAI 客户端
        model (str): 模型名称
        max_steps (int): 最大推理步数（防止无限循环）

    返回:
        tuple: (答案, 完整对话记录)
    """
    # 系统消息告诉模型三种输出格式
    system = (
        "You are a math problem solver that can use a calculator. "
        "For each step, output exactly one of:\n"
        "Thought: [your reasoning]\n"
        "Action: calculate [expression]\n"
        "Answer: [final number]\n\n"
        "When you need to compute something, use Action: calculate. "
        "You will receive the result as an Observation. "
        "When you have the final answer, use Answer:."
    )

    conversation = f"Q: {question}\n"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": conversation},
    ]

    for step in range(max_steps):
        # 让模型生成下一步（Thought/Action/Answer）
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=512,
        )
        text = response.choices[0].message.content.strip()
        messages.append({"role": "assistant", "content": text})

        # 检查是否给出了最终答案
        answer_match = re.search(r"Answer:\s*\$?([\d,]+\.?\d*)", text)
        if answer_match:
            return answer_match.group(1).replace(",", ""), text

        # 检查是否请求了计算（Action: calculate）
        calc_match = re.search(r"Action:\s*calculate\s+(.+)", text)
        if calc_match:
            expression = calc_match.group(1).strip()
            try:
                # 用 Python 的 eval() 执行计算
                # 注意：这里用 {} 限制了 eval 的上下文，防止恶意代码执行
                result = eval(expression, {"__builtins__": {}}, {})
                observation = f"Observation: {result}"
            except Exception as e:
                observation = f"Observation: Error - {e}"
            # 将计算结果作为"观察"反馈给模型
            messages.append({"role": "user", "content": observation})

    # 超过最大步数仍未得到答案，尝试从所有回答中提取
    full_text = "\n".join(
        m["content"] for m in messages if m["role"] == "assistant"
    )
    return extract_answer(full_text), full_text


# =============================================================================
# 第九部分：升级管道（Escalation Pipeline）
# =============================================================================
# 【什么是升级管道？】
# 一种"先简单后复杂"的策略：
# 1. 先用简单的 Few-Shot CoT 试一次
# 2. 再用 Self-Consistency（多次采样投票）
# 3. 如果置信度 >= 80%，直接用这个答案
# 4. 如果置信度不够，升级到更强大的 Tree-of-Thought
#
# 【为什么需要升级？】
# - 简单方法速度快、成本低，但准确率可能不够
# - 复杂方法准确率高，但速度慢、成本高
# - 升级管道在效率和准确率之间取得平衡

def solve_with_escalation(question, examples, client, model):
    """用升级管道求解：先尝试简单方法，不够好再用复杂方法。

    参数:
        question (str): 数学问题
        examples (list): 示例列表
        client: OpenAI 客户端
        model (str): 模型名称

    返回:
        dict: 包含 answer, method, confidence, votes, reasoning
    """
    # 第1步：用 Few-Shot CoT 试一次
    single_answer, single_text = few_shot_cot_solve(
        question, examples, client, model
    )

    # 第2步：用 Self-Consistency 多次采样投票
    sc_answer, confidence, reasonings, votes = self_consistency_solve(
        question, examples, client, model, n_samples=5
    )

    # 第3步：如果置信度足够高（>=80%），直接返回
    if confidence >= 0.8:
        return {
            "answer": sc_answer,
            "method": "self_consistency",
            "confidence": confidence,
            "votes": dict(votes),
            "reasoning": reasonings[0],
        }

    # 第4步：置信度不够，升级到 Tree-of-Thought
    tot_answer, tot_reasoning = tree_of_thought_solve(
        question, client, model, breadth=3, depth=2
    )

    return {
        "answer": tot_answer,
        "method": "tree_of_thought",
        "confidence": None,
        "votes": dict(votes),
        "reasoning": tot_reasoning,
    }


# =============================================================================
# 第十部分：比较测试运行器（Comparison Runner）
# =============================================================================
# 【run_comparison 做了什么？】
# 在同一组题目上运行所有4种方法，比较准确率。
#
# 【4种方法对比】
#   零样本       → 最简单，但准确率最低
#   零样本思维链  → 加一句提示词，准确率提升
#   少样本思维链  → 给示例，准确率再提升
#   自一致性     → 多次投票，准确率最高（但最贵）

def run_comparison(questions, expected_answers, examples, client, model):
    """运行4种方法的比较测试。

    参数:
        questions (list): 题目列表
        expected_answers (list): 正确答案列表
        examples (list): 少样本示例
        client: OpenAI 客户端
        model (str): 模型名称

    返回:
        dict: 每种方法的正确/总数统计
    """
    methods = {
        "zero_shot": lambda q: zero_shot_solve(q, client, model),
        "zero_shot_cot": lambda q: zero_shot_cot_solve(q, client, model),
        "few_shot_cot": lambda q: few_shot_cot_solve(q, examples, client, model),
        "self_consistency": lambda q: (
            self_consistency_solve(q, examples, client, model, n_samples=5)[:2]
        ),
    }

    results = {name: {"correct": 0, "total": 0} for name in methods}

    for i, (question, expected) in enumerate(zip(questions, expected_answers)):
        print(f"\nProblem {i + 1}: {question[:60]}...")
        for name, solver in methods.items():
            answer, *_ = solver(question)
            is_correct = str(answer) == str(expected)
            results[name]["total"] += 1
            if is_correct:
                results[name]["correct"] += 1
            status = "CORRECT" if is_correct else f"WRONG (got {answer}, expected {expected})"
            print(f"  {name:20s}: {status}")

    # 打印准确率汇总
    print("\n" + "=" * 50)
    print("ACCURACY SUMMARY")
    print("=" * 50)
    for name, counts in results.items():
        acc = counts["correct"] / counts["total"] * 100 if counts["total"] > 0 else 0
        print(f"  {name:20s}: {acc:.1f}% ({counts['correct']}/{counts['total']})")

    return results


# =============================================================================
# 第十一部分：结构化提示 + 提示链（Prompt Chaining）
# =============================================================================
# 【什么是提示链？】
# 把一个复杂任务拆成多个步骤，每个步骤用单独的提示词完成。
# 前一步的输出作为后一步的输入，形成"链条"。
#
# 【本例的3步链条】
# 第1步：提取关键数值和关系（Extract）
# 第2步：根据提取的信息列方程求解（Solve）
# 第3步：验证答案是否正确（Verify）
#
# 【为什么需要验证？】
# LLM 可能在求解时犯错。验证步骤让模型"检查自己的作业"。
# 如果验证发现问题，模型会重新求解。

def build_structured_prompt(question, context=None):
    """构建结构化提示词（用XML标签组织）。

    【为什么用XML标签？】
    XML标签可以帮助模型更好地理解提示词的结构。
    这是Anthropic Claude推荐的最佳实践。
    """
    system = """<role>
You are a precise mathematical problem solver with expertise in word problems.
</role>

<rules>
- Show all arithmetic steps explicitly
- Use one line per calculation
- State units where applicable
- End with exactly: 'The answer is [number]'
- If the problem is ambiguous, state your interpretation before solving
</rules>

<output_format>
## Interpretation
[One sentence restating the problem]

## Solution
[Step-by-step calculations]

## Answer
The answer is [number].
</output_format>"""

    user_parts = []
    if context:
        user_parts.append(f"<context>\n{context}\n</context>")
    user_parts.append(f"<problem>\n{question}\n</problem>")

    return system, "\n\n".join(user_parts)


def prompt_chain_solve(question, client, model):
    """用提示链方法求解（提取→求解→验证）。

    【3步链条】
    第1步：从题目中提取关键数值和关系
    第2步：根据提取的信息列方程并求解
    第3步：将答案代入原题验证

    参数:
        question (str): 数学问题
        client: OpenAI 客户端
        model (str): 模型名称

    返回:
        tuple: (答案, 链条详情字典)
    """
    # 第1步：提取关键信息
    extract_system = (
        "Extract the key numerical values and relationships from this math problem. "
        "List each as: [variable]: [value] [unit]. "
        "Then list each relationship as: [description]."
    )
    facts = call_llm(client, model, extract_system, question, temperature=0.0)

    # 第2步：根据提取的信息求解
    solve_system = (
        "You are a math solver. Given the extracted facts below, "
        "set up and solve the equations step by step. "
        "End with: 'The answer is [number]'."
    )
    solve_user = f"Facts:\n{facts}\n\nOriginal problem: {question}"
    solution = call_llm(client, model, solve_system, solve_user, temperature=0.0)

    # 第3步：验证答案
    verify_system = (
        "Verify this math solution by plugging the answer back into "
        "the original problem. Does it check out? "
        "If yes, restate: 'The answer is [number]'. "
        "If no, solve it correctly and state: 'The answer is [number]'."
    )
    verify_user = f"Problem: {question}\n\nProposed solution:\n{solution}"
    verified = call_llm(client, model, verify_system, verify_user, temperature=0.0)

    return extract_answer(verified), {
        "facts": facts,
        "solution": solution,
        "verification": verified,
    }


# =============================================================================
# 第十二部分：测试题目（Test Questions）
# =============================================================================
# 【GSM8K 测试集】
# 这些题目来自 GSM8K 数据集，用于测试各种提示技术的效果。
# 每道题都有确定的数字答案，方便自动评估。

TEST_QUESTIONS = [
    {
        "question": (
            "Natalia sold clips to 48 of her friends in April, "
            "and then she sold half as many clips in May. "
            "How many clips did Natalia sell altogether in April and May?"
        ),
        "answer": "72",  # 48 + 48/2 = 48 + 24 = 72
    },
    {
        "question": (
            "Weng earns $12 an hour for babysitting. Yesterday, she just "
            "did 50 minutes of babysitting. How much did she earn?"
        ),
        "answer": "10",  # 12 * 50/60 = 10
    },
    {
        "question": (
            "Betty is saving money for a new wallet which costs $100. "
            "Betty has only half of the money she needs. Her parents decided "
            "to give her $15 for that purpose, and her grandparents twice as "
            "much as her parents. How much more money does Betty need to buy "
            "the wallet?"
        ),
        "answer": "5",  # 100 - 50 - 15 - 30 = 5
    },
    {
        "question": (
            "Julie is reading a 120-page book. Yesterday, she was able to "
            "read 12 pages and today, she read twice as many pages as yesterday. "
            "If she wants to read half of the remaining pages tomorrow, "
            "how many pages should she read?"
        ),
        "answer": "42",  # 120 - 12 - 24 = 84, 84/2 = 42
    },
    {
        "question": (
            "James writes a 3-page letter to 2 different friends twice a week. "
            "How many pages does he write a year?"
        ),
        "answer": "624",  # 3 * 2 * 2 * 52 = 624
    },
]


# =============================================================================
# 主程序入口
# =============================================================================
# 【运行顺序】
# 1. 比较4种提示技术的准确率
# 2. 演示升级管道（先简单后复杂）
# 3. 演示提示链（提取→求解→验证）
# 4. 演示 ReAct（推理+计算器）
#
# 【运行前提】
# 需要设置环境变量 OPENAI_API_KEY
# 运行: python advanced_prompting.py

if __name__ == "__main__":
    # 初始化 OpenAI 客户端
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"))
    model = "gpt-4o"

    print("=" * 60)
    print("ADVANCED PROMPTING PIPELINE")
    print("Few-Shot + CoT + Self-Consistency + Tree-of-Thought")
    print("=" * 60)

    questions = [t["question"] for t in TEST_QUESTIONS]
    expected = [t["answer"] for t in TEST_QUESTIONS]

    # 第1部分：4种技术的准确率比较
    print("\n--- Technique Comparison ---")
    run_comparison(questions, expected, GSM8K_EXAMPLES, client, model)

    # 第2部分：升级管道演示
    print("\n\n--- Escalation Pipeline ---")
    for test in TEST_QUESTIONS[:2]:
        print(f"\nQ: {test['question'][:80]}...")
        result = solve_with_escalation(
            test["question"], GSM8K_EXAMPLES, client, model
        )
        print(f"  Method: {result['method']}")
        print(f"  Answer: {result['answer']} (expected: {test['answer']})")
        print(f"  Confidence: {result['confidence']}")

    # 第3部分：提示链演示
    print("\n\n--- Prompt Chaining ---")
    for test in TEST_QUESTIONS[:2]:
        print(f"\nQ: {test['question'][:80]}...")
        answer, chain = prompt_chain_solve(test["question"], client, model)
        print(f"  Answer: {answer} (expected: {test['answer']})")
        print(f"  Steps: extract -> solve -> verify")

    # 第4部分：ReAct 演示
    print("\n\n--- ReAct ---")
    for test in TEST_QUESTIONS[:2]:
        print(f"\nQ: {test['question'][:80]}...")
        answer, trace = react_solve(test["question"], client, model)
        print(f"  Answer: {answer} (expected: {test['answer']})")

    print("\n\nDone.")