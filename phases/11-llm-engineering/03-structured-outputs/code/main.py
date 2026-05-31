# =============================================================================
# 结构化输出（Structured Outputs）：JSON Schema 验证 + 约束解码 + 提取管道
# 本文件对应课程文档：phases/11-llm-engineering/03-structured-outputs/docs/zh.md
# 参考来源：
#   - JSON Schema 规范: https://json-schema.org/
#   - OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
# =============================================================================
#
# 【初学者导读】
# LLM 生成的通常是自由文本，但很多应用需要结构化数据（如 JSON）。
# 本文件展示了3个核心技术，确保 LLM 的输出是合法的结构化数据：
#
#   1. JSON Schema 验证 - 定义数据的"形状"，检查 LLM 输出是否符合
#   2. 约束解码（Constrained Decoding）- 在生成时限制模型只能输出合法的 token
#   3. 提取管道 + 重试 - 从文本中提取结构化数据，失败则重试
#
# 【为什么需要结构化输出？】
# 想象你让 LLM 分析一条评论的情感。如果它回答：
#   "我觉得这条评论是正面的" → 很难用程序解析
#   {"sentiment": "positive", "confidence": 0.9} → 直接可用！
#
# 【三种控制输出格式的方法】
#   方法1：在提示词中要求输出 JSON（最简单，但不保证格式正确）
#   方法2：用 JSON Schema 验证输出（事后检查）
#   方法3：用约束解码（事前控制，保证输出一定合法）
#
# 【运行方式】
# python main.py（无需 API 密钥，使用模拟数据）
#

import json


# =============================================================================
# 第一部分：JSON Schema 验证器（Schema Validator）
# =============================================================================
# 【什么是 JSON Schema？】
# JSON Schema 是一种描述 JSON 数据"形状"的标准。
# 例如，你可以说："产品数据必须有 name(字符串)、price(数字≥0)、in_stock(布尔值)"
# 然后用 Schema 来检查任意 JSON 是否符合这个形状。
#
# 【支持的类型】
#   - object:  对象（字典），有 properties 和 required 字段
#   - array:   数组（列表），有 items 类型和长度限制
#   - string:  字符串，可选 enum 枚举值
#   - number:  数字，可选 min/max 范围
#   - integer: 整数
#   - boolean: 布尔值
#
# 【递归验证】
# Schema 可以嵌套（对象里有对象，数组里有对象），
# 所以验证器用递归方式遍历整个数据结构。

def validate_schema(data, schema):
    """验证数据是否符合 JSON Schema。

    参数:
        data: 要验证的数据（Python 对象）
        schema (dict): JSON Schema 定义

    返回:
        list: 错误信息列表，空列表表示验证通过

    示例:
        >>> validate_schema({"name": "Alice", "age": 30}, {"type": "object", "properties": {"name": {"type": "string"}, "age": {"type": "integer"}}, "required": ["name"]})
        []
        >>> validate_schema({"name": 123}, {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]})
        ['.name: expected string, got int']
    """
    errors = []
    _validate(data, schema, "", errors)
    return errors


def _validate(data, schema, path, errors):
    """递归验证的核心函数。

    参数:
        data: 当前要验证的数据
        schema (dict): 当前层级的 Schema 定义
        path (str): 当前的路径（如 ".customer.name"），用于错误信息
        errors (list): 错误信息收集列表
    """
    schema_type = schema.get("type")

    # --- 验证对象类型 ---
    if schema_type == "object":
        # 先检查数据本身是不是字典
        if not isinstance(data, dict):
            errors.append(f"{path}: expected object, got {type(data).__name__}")
            return
        # 检查所有必填字段是否存在
        for key in schema.get("required", []):
            if key not in data:
                errors.append(f"{path}.{key}: required field missing")
        # 递归验证每个属性
        properties = schema.get("properties", {})
        for key, value in data.items():
            if key in properties:
                _validate(value, properties[key], f"{path}.{key}", errors)

    # --- 验证数组类型 ---
    elif schema_type == "array":
        if not isinstance(data, list):
            errors.append(f"{path}: expected array, got {type(data).__name__}")
            return
        # 检查数组长度
        min_items = schema.get("minItems", 0)
        max_items = schema.get("maxItems", float("inf"))
        if len(data) < min_items:
            errors.append(f"{path}: array has {len(data)} items, minimum is {min_items}")
        if len(data) > max_items:
            errors.append(f"{path}: array has {len(data)} items, maximum is {max_items}")
        # 递归验证数组中的每个元素
        items_schema = schema.get("items", {})
        for i, item in enumerate(data):
            _validate(item, items_schema, f"{path}[{i}]", errors)

    # --- 验证字符串类型 ---
    elif schema_type == "string":
        if not isinstance(data, str):
            errors.append(f"{path}: expected string, got {type(data).__name__}")
            return
        # 检查枚举值（如果定义了 enum）
        enum_values = schema.get("enum")
        if enum_values and data not in enum_values:
            errors.append(f"{path}: '{data}' not in allowed values {enum_values}")

    # --- 验证数字类型 ---
    elif schema_type == "number":
        if not isinstance(data, (int, float)):
            errors.append(f"{path}: expected number, got {type(data).__name__}")
            return
        # 检查最小值和最大值
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and data < minimum:
            errors.append(f"{path}: {data} is less than minimum {minimum}")
        if maximum is not None and data > maximum:
            errors.append(f"{path}: {data} is greater than maximum {maximum}")

    # --- 验证布尔类型 ---
    elif schema_type == "boolean":
        if not isinstance(data, bool):
            errors.append(f"{path}: expected boolean, got {type(data).__name__}")

    # --- 验证整数类型 ---
    elif schema_type == "integer":
        # Python 中 bool 是 int 的子类，所以需要排除
        if not isinstance(data, int) or isinstance(data, bool):
            errors.append(f"{path}: expected integer, got {type(data).__name__}")


# =============================================================================
# 第二部分：Python 类型到 Schema 的转换器
# =============================================================================
# 【SchemaField 类】
# 用 Python 类来声明字段的类型和约束，然后自动转换为 JSON Schema。
# 这比手写 JSON Schema 更方便、更不容易出错。
#
# 【设计思路】
# 你可以用 Python 类型（str, int, float, bool, list）来声明字段，
# 然后用 model_to_schema() 自动生成 JSON Schema。
# 这类似于 Pydantic 的设计思想，但更简单。

class SchemaField:
    """表示一个 Schema 字段的定义。

    参数:
        field_type: Python 类型（str, int, float, bool, list）
        required (bool): 是否必填，默认 True
        default: 默认值
        enum (list): 枚举值列表（只允许这些值）
        minimum (float): 最小值
        maximum (float): 最大值
    """
    def __init__(self, field_type, required=True, default=None, enum=None, minimum=None, maximum=None):
        self.field_type = field_type
        self.required = required
        self.default = default
        self.enum = enum
        self.minimum = minimum
        self.maximum = maximum


def python_type_to_schema(field):
    """将 Python 类型的 SchemaField 转换为 JSON Schema 片段。

    【类型映射表】
    Python 类型 → JSON Schema 类型：
    - str   → "string"
    - int   → "integer"
    - float → "number"
    - bool  → "boolean"
    - list  → "array"（默认元素类型为 string）
    """
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
    }

    schema = {}

    # 基本类型映射
    if field.field_type in type_map:
        schema["type"] = type_map[field.field_type]
    elif field.field_type == list:
        schema["type"] = "array"
        schema["items"] = {"type": "string"}  # 默认数组元素为字符串
    elif isinstance(field.field_type, dict):
        schema = field.field_type  # 直接使用自定义 schema

    # 附加约束
    if field.enum:
        schema["enum"] = field.enum
    if field.minimum is not None:
        schema["minimum"] = field.minimum
    if field.maximum is not None:
        schema["maximum"] = field.maximum

    return schema


def model_to_schema(name, fields):
    """将 Python 模型转换为完整的 JSON Schema。

    参数:
        name (str): 模型名称（用于文档，不影响验证）
        fields (dict): {字段名: SchemaField} 的字典

    返回:
        dict: 完整的 JSON Schema

    示例:
        >>> schema = model_to_schema("Product", {
        ...     "name": SchemaField(str),
        ...     "price": SchemaField(float, minimum=0),
        ... })
        >>> # 返回 {"type": "object", "properties": {...}, "required": ["name", "price"]}
    """
    properties = {}
    required = []

    for field_name, field in fields.items():
        properties[field_name] = python_type_to_schema(field)
        if field.required:
            required.append(field_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


# =============================================================================
# 第三部分：约束解码（Constrained Decoding）
# =============================================================================
# 【什么是约束解码？】
# 在模型生成每个 token 时，根据当前的 JSON 状态，
# 限制模型只能选择"合法"的下一个 token。
#
# 【工作原理（类比）】
# 想象你在填一个表格：
# - 如果当前是空的 → 下一个字符必须是 "{"
# - 如果刚写了 "{" → 下一个必须是 '"'（开始一个键）或 "}"（空对象）
# - 如果刚写了 "key": → 下一个必须是值（字符串、数字、布尔等）
#
# 这样从第一个字符到最后一个字符，每一步都只能选合法的字符，
# 最终输出的一定是合法的 JSON！
#
# 【next_valid_tokens 做了什么？】
# 给定一个部分 JSON 字符串，返回下一个合法的 token 类型列表。
# 这个函数是约束解码的核心逻辑。

def next_valid_tokens(partial_json, schema):
    """根据当前的部分 JSON，计算下一个合法的 token。

    参数:
        partial_json (str): 当前已生成的部分 JSON 字符串
        schema (dict): JSON Schema（本函数中未使用，仅用于未来扩展）

    返回:
        list: 下一个合法 token 的描述列表

    示例:
        >>> next_valid_tokens("", {})
        ['{']
        >>> next_valid_tokens("{", {})
        ['"', '}']
        >>> next_valid_tokens('{"name":', {})
        ['"', '0-9', 'true', 'false', 'null', '[', '{']
    """
    stripped = partial_json.strip()

    # 空字符串：必须以 "{" 开始
    if not stripped:
        return ["{"]

    # 如果已经是一个完整的 JSON，返回结束标记
    try:
        json.loads(stripped)
        return ["<EOS>"]  # End Of String
    except json.JSONDecodeError:
        pass

    # 根据最后一个字符判断下一步合法的 token
    last_char = stripped[-1] if stripped else ""

    if last_char == "{":
        # 在 "{" 后面：可以开始一个键（"）或直接结束（}）
        return ['"', "}"]
    elif last_char == '"':
        if stripped.endswith('":'):
            # 在 "key": 后面：需要一个值
            return ['"', "0-9", "true", "false", "null", "[", "{"]
        # 在一个字符串中间：继续输入字符或结束字符串
        return ["a-z", '"']
    elif last_char == ":":
        # 在 ":" 后面：需要一个值
        return [" ", '"', "0-9", "true", "false", "null", "[", "{"]
    elif last_char == ",":
        # 在 "," 后面：需要下一个键值对
        return [" ", '"', "{", "["]
    elif last_char in "0123456789":
        # 在数字后面：继续数字、小数点、或结束
        return ["0-9", ".", ",", "}", "]"]
    elif last_char == "}":
        # 在 "}" 后面：可以继续逗号（更多字段）或结束
        return [",", "}", "]", "<EOS>"]
    elif last_char == "]":
        # 在 "]" 后面：可以继续逗号或结束
        return [",", "}", "<EOS>"]
    elif last_char == "[":
        # 在 "[" 后面：需要数组元素或直接结束
        return ['"', "0-9", "true", "false", "null", "{", "[", "]"]
    else:
        return ["any"]


# =============================================================================
# 第四部分：模拟 LLM 提取 + 重试机制
# =============================================================================
# 【simulate_llm_extraction】
# 模拟从文本中提取产品信息。实际项目中，这里会调用真正的 LLM API。
#
# 【extract_with_retry 的重试机制】
# LLM 的输出不总是完美的。重试机制的工作流程：
# 1. 调用 LLM 获取 JSON 输出
# 2. 尝试解析 JSON（可能语法错误）
# 3. 用 Schema 验证（可能字段缺失或类型不对）
# 4. 如果失败，重试（最多 max_retries 次）
# 5. 如果所有重试都失败，返回 None

def simulate_llm_extraction(text, schema, attempt=0):
    """模拟 LLM 从文本中提取结构化数据。

    【注意】这是模拟函数，实际项目中应替换为真实的 LLM API 调用。
    模拟不同场景：耳机产品、笔记本电脑、键盘等。

    参数:
        text (str): 输入文本
        schema (dict): 期望的 JSON Schema
        attempt (int): 当前重试次数（不同次数可能返回不同结果）

    返回:
        str: JSON 格式的字符串
    """
    if "headphones" in text.lower() or "sony" in text.lower():
        if attempt == 0:
            return '{"product": "Sony WH-1000XM5", "price": 348.00, "in_stock": true, "categories": ["audio", "headphones"]}'
        return '{"product": "Sony WH-1000XM5", "price": 348.00, "in_stock": true}'

    if "laptop" in text.lower() or "macbook" in text.lower():
        return '{"product": "MacBook Pro 16", "price": 2499.00, "in_stock": false, "categories": ["computers"]}'

    if "keyboard" in text.lower():
        return '{"product": "Keychron Q1", "price": 169.00, "in_stock": true, "categories": ["peripherals"]}'

    return '{"product": "Unknown", "price": 0, "in_stock": false}'


def extract_with_retry(text, schema, max_retries=3):
    """从文本中提取结构化数据，失败时自动重试。

    【重试逻辑】
    1. 调用 LLM 获取 JSON 字符串
    2. 解析 JSON（json.loads）
    3. 用 Schema 验证（validate_schema）
    4. 如果通过，返回数据
    5. 如果失败，打印错误信息并重试
    6. 所有重试都失败则返回 None

    参数:
        text (str): 输入文本
        schema (dict): JSON Schema
        max_retries (int): 最大重试次数

    返回:
        dict 或 None: 解析成功返回字典，失败返回 None
    """
    for attempt in range(max_retries):
        # 调用（模拟的）LLM
        raw = simulate_llm_extraction(text, schema, attempt)

        # 第1步：尝试解析 JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"    Attempt {attempt + 1}: JSON parse error -- {e}")
            continue  # JSON 语法错误，重试

        # 第2步：用 Schema 验证
        errors = validate_schema(data, schema)
        if not errors:
            return data  # 验证通过，返回数据

        print(f"    Attempt {attempt + 1}: Schema validation errors -- {errors}")

    return None  # 所有重试都失败


# =============================================================================
# 第五部分：产品 Schema 定义
# =============================================================================
# 【这是一个典型的"产品信息提取"Schema】
# 从文本中提取：产品名称、价格、是否有货、分类
#
# 【required vs 可选字段】
# required: ["product", "price", "in_stock"]  → 这3个字段必须存在
# "categories" 是可选的（不在 required 中）→ 可以缺失

PRODUCT_SCHEMA = {
    "type": "object",
    "properties": {
        "product": {"type": "string"},
        "price": {"type": "number", "minimum": 0},
        "in_stock": {"type": "boolean"},
        "categories": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["product", "price", "in_stock"],
}


# =============================================================================
# 第六部分：演示函数（Demo Functions）
# =============================================================================

def run_schema_validation_demo():
    """演示 JSON Schema 验证的各种场景。

    【测试用例说明】
    1. 合法的完整对象 → 应该通过
    2. 合法对象 + 可选数组 → 应该通过
    3. 负数价格 → 应该失败（minimum=0）
    4. 缺少必填字段 → 应该失败
    5. 用字符串代替数字 → 应该失败（类型错误）
    6. 用数字代替字符串 → 应该失败（类型错误）
    7. 用字符串代替对象 → 应该失败（类型错误）
    8. 用字符串代替布尔值 → 应该失败（类型错误）
    """
    print("=" * 60)
    print("  STEP 1: JSON Schema Validation")
    print("=" * 60)

    test_cases = [
        ({"product": "Sony WH-1000XM5", "price": 348.0, "in_stock": True}, "Valid complete object"),
        ({"product": "Test", "price": 10.0, "in_stock": True, "categories": ["audio"]}, "Valid with optional array"),
        ({"product": "Test", "price": -5.0, "in_stock": True}, "Negative price"),
        ({"product": "Test", "in_stock": True}, "Missing required field (price)"),
        ({"product": "Test", "price": "ten", "in_stock": True}, "String as price"),
        ({"product": 123, "price": 10.0, "in_stock": True}, "Number as product name"),
        ("not an object", "String instead of object"),
        ({"product": "Test", "price": 10.0, "in_stock": "yes"}, "String as boolean"),
    ]

    for data, label in test_cases:
        errors = validate_schema(data, PRODUCT_SCHEMA)
        status = "PASS" if not errors else f"FAIL: {errors}"
        print(f"\n  {label}:")
        print(f"    Data:   {json.dumps(data) if isinstance(data, dict) else repr(data)}")
        print(f"    Result: {status}")


def run_schema_generation_demo():
    """演示从 Python 类型自动生成 JSON Schema。"""
    print(f"\n{'=' * 60}")
    print("  STEP 2: Model-to-Schema Generation")
    print("=" * 60)

    # 定义产品模型
    product_fields = {
        "product": SchemaField(str),                                # 产品名：字符串，必填
        "price": SchemaField(float, minimum=0),                     # 价格：浮点数，≥0，必填
        "in_stock": SchemaField(bool),                              # 有货：布尔值，必填
        "categories": SchemaField(list, required=False),            # 分类：字符串数组，可选
        "rating": SchemaField(float, required=False, minimum=0, maximum=5),  # 评分：0-5，可选
    }

    schema = model_to_schema("Product", product_fields)
    print(f"\n  Generated schema from Python model:")
    print(f"  {json.dumps(schema, indent=2)}")

    # 定义事件模型
    event_fields = {
        "title": SchemaField(str),
        "date": SchemaField(str),
        "attendees": SchemaField(list),
        "priority": SchemaField(str, enum=["low", "medium", "high"]),  # 枚举：只允许这3个值
        "is_recurring": SchemaField(bool, required=False),
    }

    event_schema = model_to_schema("Event", event_fields)
    print(f"\n  Event schema:")
    print(f"  {json.dumps(event_schema, indent=2)}")

    # 验证事件数据
    valid_event = {"title": "Standup", "date": "2026-01-15", "attendees": ["Alice", "Bob"], "priority": "high"}
    invalid_event = {"title": "Standup", "date": "2026-01-15", "attendees": ["Alice"], "priority": "urgent"}  # "urgent" 不在枚举中

    print(f"\n  Validating against event schema:")
    for data, label in [(valid_event, "Valid event"), (invalid_event, "Invalid priority enum")]:
        errors = validate_schema(data, event_schema)
        status = "PASS" if not errors else f"FAIL: {errors}"
        print(f"    {label}: {status}")


def run_constrained_decoding_demo():
    """演示约束解码的过程。"""
    print(f"\n{'=' * 60}")
    print("  STEP 3: Constrained Decoding Simulation")
    print("=" * 60)
    demonstrate_constrained_decoding()


def demonstrate_constrained_decoding():
    """展示 JSON 逐步生成过程中，每一步合法的下一个 token。

    【演示过程】
    从空字符串开始，逐步构建 JSON：
    "" → "{" → '{"product"' → '{"product":' → ...
    每一步都展示哪些字符是合法的下一个输入。
    """
    partial_states = [
        "",
        "{",
        '{"product"',
        '{"product":',
        '{"product": "Sony"',
        '{"product": "Sony",',
        '{"product": "Sony", "price":',
        '{"product": "Sony", "price": 348',
        '{"product": "Sony", "price": 348}',
    ]

    print(f"\n  {'Partial JSON':<45} {'Valid Next Tokens'}")
    print("  " + "-" * 70)
    for state in partial_states:
        valid = next_valid_tokens(state, {})
        display = state if state else "(empty)"
        print(f"  {display:<45} {valid}")


def run_extraction_pipeline_demo():
    """演示完整的提取管道：从文本到结构化数据。"""
    print(f"\n{'=' * 60}")
    print("  STEP 4: Extraction Pipeline with Retry")
    print("=" * 60)

    texts = [
        "The Sony WH-1000XM5 headphones are priced at $348 and currently available in stores.",
        "The new MacBook Pro 16-inch laptop costs $2499 but is completely sold out everywhere.",
        "I just bought a Keychron Q1 mechanical keyboard for $169 and it arrived today.",
        "This sentence contains no product information at all.",
    ]

    for text in texts:
        print(f"\n  Input: {text[:70]}...")
        result = extract_with_retry(text, PRODUCT_SCHEMA)
        if result:
            print(f"  Output: {json.dumps(result)}")
        else:
            print(f"  Output: FAILED after retries")


def run_nested_schema_demo():
    """演示嵌套 Schema 验证（对象中有对象，数组中有对象）。

    【订单 Schema 的结构】
    订单 {
        order_id: 字符串
        customer: {
            name: 字符串
            email: 字符串（必填）
        }
        items: [{
            product: 字符串
            quantity: 整数
            price: 数字（≥0）
        }]
        total: 数字（≥0）
    }
    """
    print(f"\n{'=' * 60}")
    print("  STEP 5: Nested Schema Validation")
    print("=" * 60)

    order_schema = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "customer": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                },
                "required": ["name", "email"],
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product": {"type": "string"},
                        "quantity": {"type": "integer"},
                        "price": {"type": "number", "minimum": 0},
                    },
                    "required": ["product", "quantity", "price"],
                },
                "minItems": 1,  # 至少要有一个商品
            },
            "total": {"type": "number", "minimum": 0},
        },
        "required": ["order_id", "customer", "items", "total"],
    }

    # 合法订单
    valid_order = {
        "order_id": "ORD-001",
        "customer": {"name": "Alice", "email": "alice@example.com"},
        "items": [
            {"product": "Widget", "quantity": 3, "price": 9.99},
            {"product": "Gadget", "quantity": 1, "price": 24.99},
        ],
        "total": 54.96,
    }

    # 非法订单（缺少 email、空商品列表、负数总价）
    invalid_order = {
        "order_id": "ORD-002",
        "customer": {"name": "Bob"},           # 缺少 email
        "items": [],                            # 空列表（minItems=1）
        "total": -10,                           # 负数（minimum=0）
    }

    print(f"\n  Order schema (nested objects + arrays):")
    for data, label in [(valid_order, "Valid order"), (invalid_order, "Invalid order")]:
        errors = validate_schema(data, order_schema)
        status = "PASS" if not errors else f"FAIL"
        print(f"\n    {label}: {status}")
        if errors:
            for e in errors:
                print(f"      - {e}")


# =============================================================================
# 主程序入口
# =============================================================================
# 【运行顺序】
# 1. Schema 验证演示：展示合法和非法数据的验证结果
# 2. Schema 生成演示：从 Python 类型自动生成 JSON Schema
# 3. 约束解码演示：展示 JSON 生成过程中每一步的合法 token
# 4. 提取管道演示：从文本提取结构化数据（带重试）
# 5. 嵌套 Schema 演示：验证复杂的嵌套数据结构

if __name__ == "__main__":
    run_schema_validation_demo()       # Schema 验证
    run_schema_generation_demo()       # Schema 生成
    run_constrained_decoding_demo()    # 约束解码
    run_extraction_pipeline_demo()     # 提取管道
    run_nested_schema_demo()           # 嵌套 Schema