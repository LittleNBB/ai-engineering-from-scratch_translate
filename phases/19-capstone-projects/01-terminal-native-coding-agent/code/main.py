"""Terminal-native coding agent — minimal plan/act/observe loop scaffold.

The hard architectural primitive in a 2026 coding agent is not the model call
or any single tool. It is the plan-act-observe-recover loop with bounded
context, a structured plan state, a sandboxed tool dispatcher, and hook
callbacks at every lifecycle point. This file implements that loop end to end
in stdlib Python. The LLM is stubbed out with a deterministic script so the
loop logic stays observable and testable without network calls.

Run:  python main.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import ast #tree_sitter无法安装,先用ast做个简单的替代,只能解析python文件,不过足够演示了
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable
import openai
import tempfile

# 这个函数的作用是从当前目录及其父目录中加载 .env 文件中的环境变量，以便在运行 main() 函数之前设置好所需的环境变量。它会从当前文件所在的目录开始，逐级向上查找 .env 文件，直到找到为止或者达到文件系统根目录。如果找到了 .env 文件，就会读取其中的每一行，将非空且非注释的行解析为 key=value 的形式，并将这些键值对设置为环境变量。这样做可以方便地在本地开发环境中管理敏感信息和配置参数，而不需要将它们硬编码在代码中。
def load_dotenv() -> None:
    """Load environment variables from a .env file in the current directory."""
    path = os.path.dirname(os.path.abspath(__file__))
    while True:
        env_path = os.path.join(path, ".env")
        if os.path.exists(env_path):
            break
        parent = os.path.dirname(path)
        if parent == path:
            return  # reached root without finding .env
        path = parent #move up on directory and check again

    with open(env_path, "r") as f:
        for line in f:
            line = line.strip() # skip empty lines and comments
            if not line or line.startswith("#"): #跳过注释和空行
                continue
            key, _, value = line.partition("=") #作用是将每行按第一个等号分成三部分：key、分隔符（丢弃）和value
            os.environ.setdefault(key.strip(), value.strip()) #将key和value去除两端空白后设置为环境变量

load_dotenv()

# 配置llm客户端
client = openai.OpenAI(
    api_key = os.environ.get("MIMO_API_KEY", ""), 
    # 第二个参数是默认值，如果环境变量 API_KEY 没有设置，则使用空字符串作为默认值。这种方式可以避免在没有设置环境变量的情况下抛出 KeyError 异常，同时也允许在需要时提供一个默认的 API 密钥。
    base_url = os.environ.get("MIMO_BASE_URL","https://token-plan-cn.xiaomimimo.com/v1"),
)
#系统提示要放在外面,不能放在 run_agent 里,因为它是固定不变的,放在外面可以避免每次调用 run_agent 都重复定义这个提示文本,节省内存和提高效率。
SYSTEM_PROMPT = """你是一个编程 Agent。你可以使用以下工具：

1. read_file(path) — 读取文件内容
2. run_shell(cmd) — 执行 shell 命令
3. edit_file(path, start_line, end_line, new_content) — 编辑文件，替换指定行的内容
4. ripgrep(pattern, glob) — 在代码库中搜索文本（glob 可选，如 "*.py"）
5. tree_sitter_symbols(path) — 解析 Python 文件，提取函数和类定义
6. git(subcmd) — 执行 git 命令（仅允许 status / diff / log / branch）

每轮你需要：
1. 更新计划状态（每个步骤标记 pending/in_progress/done/failed）
2. 决定下一步使用哪个工具，或者决定完成任务

你必须严格以 JSON 格式回复，不要输出任何其他内容：
{
  "plan": [["步骤描述", "状态"], ...],
  "tool": "工具名",
  "args": {"参数名": "参数值"}
}

如果任务已完成，tool 设为 null：
{
  "plan": [["步骤描述", "done"]],
  "tool": null
}
重要规则：
- 如果工具返回 "exit=0" 或 "(command succeeded with no output)"，说明命令执行成功，请立即标记该步骤为 "done" 并进入下一步。
- 不要重复执行同一个命令。
- 不要尝试用不同的方式做同一件事。

"""


# ---------------------------------------------------------------------------
# plan state  --  TodoWrite shape, rewritten whole each turn
# §14.01 agent-loop  §14.02 rewoo  §14.11 planning-htn
# ---------------------------------------------------------------------------

@dataclass
class TodoItem:
    id: int
    description: str
    status: str  # "pending" | "in_progress" | "done" | "failed"
    note: str = ""


@dataclass
class PlanState:
    goal: str
    items: list[TodoItem] = field(default_factory=list)  # 每个实例独立初始化空列表，避免多个 PlanState 共享同一个可变默认对象

    def summary(self) -> str:
        lines = [f"GOAL: {self.goal}"]
        for it in self.items:
            mark = {"pending": " ", "in_progress": ">", "done": "x", "failed": "!"}[it.status]
            lines.append(f"  [{mark}] {it.id}. {it.description}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# budget  --  hard ceilings on turns, tokens, dollars
# §14.01 agent-loop  §14.29 production-runtimes
# ---------------------------------------------------------------------------

@dataclass
class Budget:
    max_turns: int = 50
    max_tokens: int = 200_000
    max_dollars: float = 5.00
    turns_used: int = 0
    tokens_used: int = 0
    dollars_used: float = 0.0

    def step(self, tokens: int, dollars: float) -> None:
        self.turns_used += 1
        self.tokens_used += tokens
        self.dollars_used += dollars

    def exceeded(self) -> str | None:
        if self.turns_used >= self.max_turns:
            return "turn_limit"
        if self.tokens_used >= self.max_tokens:
            return "token_limit"
        if self.dollars_used >= self.max_dollars:
            return "dollar_limit"
        return None


# ---------------------------------------------------------------------------
# hooks  --  2026 eight-event surface (Pre/PostToolUse, SessionStart/End, etc)
# §14.17 claude-agent-sdk
# ---------------------------------------------------------------------------

HookFn = Callable[[dict[str, Any]], dict[str, Any]]


class HookBus:
    EVENTS = ("SessionStart", "SessionEnd", "PreToolUse", "PostToolUse",
              "UserPromptSubmit", "Notification", "Stop", "PreCompact")

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookFn]] = {e: [] for e in self.EVENTS}

    def on(self, event: str, fn: HookFn) -> None:
        self._hooks[event].append(fn)

    def fire(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        for fn in self._hooks[event]:
            payload = fn(payload) or payload
        return payload


# ---------------------------------------------------------------------------
# tool surface  --  six tools, each sandboxed, each returns truncated text
# §13  tools-and-protocols  §14.06 tool-use-and-function-calling
# ---------------------------------------------------------------------------

TRUNCATE_BYTES = 4096


def tool_read_file(sandbox: str, path: str) -> str:
    full = os.path.join(sandbox, path)
    if not os.path.realpath(full).startswith(os.path.realpath(sandbox)):
        raise RuntimeError("path escapes sandbox")
    with open(full, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()[:TRUNCATE_BYTES]
    
def tool_edit_file(sandbox: str, path:str, start_line: int, end_line: int, new_content: str) -> str:
    """编辑文件,替换指定行范围的内容为新的内容。"""
    full = os.path.join(sandbox, path)
    #防止路径逃逸
    if not os.path.realpath(full).startswith(os.path.realpath(sandbox)):
        raise RuntimeError("path escapes sandbox")

    with open(full, "r", encoding = "utf-8", errors = "replace") as fh:
        lines = fh.readlines()

    before = "".join(lines[start_line -1:end_line]) 
    #获取要替换的行范围的原始内容
    lines[start_line -1:end_line] = [new_content + "\n"] 
    #替换指定行范围的内容为新的内容
    with open(full, "w", encoding = "utf-8", errors = "replace") as fh:
        fh.writelines(lines)

    return f"edited{path}lines {start_line}-{end_line}\n---before---\n{before}---after---\n{new_content[:TRUNCATE_BYTES]}"

def tool_ripgrep(sandbox: str, pattern: str, glob: str) -> str:
    cmd = f'findstr /S /N /P "{pattern}" *'
    #findstr 是 Windows 上的一个命令行工具，用于在文件中搜索指定的字符串。/S 参数表示递归搜索当前目录及其子目录中的所有文件，/N 参数表示在输出结果中显示行号，/P 参数表示在搜索时忽略二进制文件。"{pattern}" 是要搜索的字符串模式，* 表示搜索所有文件。
    if glob:
        cmd += f' --include "{glob}"'
    #glob 是一个通配符模式，用于指定要搜索的文件类型或名称。例如，*.txt 表示只搜索以 .txt 结尾的文本文件。如果 glob 参数不为空，就将 --include "{glob}" 添加到命令中，以限制搜索范围。

    proc = subprocess.run(cmd, cwd=sandbox, shell=True, capture_output=True,
                          text=True, timeout=30, encoding="utf-8", errors="replace")
    #subprocess.run() 函数用于在 Python 中执行外部命令。它接受一个命令字符串 cmd，并在指定的工作目录 sandbox 中执行该命令。shell=True 表示通过 shell 来执行命令，这样可以使用 shell 的功能和语法。capture_output=True 表示捕获命令的标准输出和标准错误输出，以便后续处理。text=True 表示将输出作为文本处理，而不是字节流。timeout=30 表示如果命令执行超过 30 秒，就会抛出 TimeoutExpired 异常。encoding="utf-8" 和 errors="replace" 用于处理输出的编码和错误，确保能够正确读取输出内容。
    out = (proc.stdout + proc.stderr)[:TRUNCATE_BYTES]
    #proc.stdout 是命令执行成功时的标准输出，proc.stderr 是命令执行失败时的错误输出。将两者相加可以确保无论命令执行成功还是失败，都能获取到相关的输出信息。[:TRUNCATE_BYTES] 表示只保留输出的前 TRUNCATE_BYTES 字节，以避免返回过多的数据。
    if not out.strip():
        return "no matches"
    return out

def tool_tree_sitter_symbols(sandbox: str, path: str) -> str:
    """解析文件,提取函数和类的定义,返回一个结构化的符号列表。"""
    full = os.path.join(sandbox, path)
    if not os.path.realpath(full).startswith(os.path.realpath(sandbox)):
        raise RuntimeError("path escapes sandbox")
    
    with open(full, "r", encoding="utf-8", errors="replace") as fh:
        source = fh.read()

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"Syntax error in {path}: {e}"

    symbols = [] 
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            symbols.append(f"Function: {node.name} at line {node.lineno}")
        elif isinstance(node, ast.ClassDef):
            symbols.append(f"Class: {node.name} at line {node.lineno}")
    #ast.walk() 函数用于遍历抽象语法树中的所有节点。对于每个节点，如果它是 ast.FunctionDef 类型，表示一个函数定义，就将函数的名称和所在行号添加到符号列表中；如果它是 ast.ClassDef 类型，表示一个类定义，就将类的名称和所在行号添加到符号列表中。最终返回一个包含所有函数和类定义的符号列表。
    if not symbols:
        return "no symbols found"
    return "\n".join(symbols)


def tool_run_shell(sandbox: str, cmd: str, timeout: int = 30) -> str:
    proc = subprocess.run(cmd, cwd=sandbox, shell=True, capture_output=True,
                          text=True, timeout=timeout, encoding="utf-8", errors="replace")
    out = (proc.stdout + proc.stderr)[:TRUNCATE_BYTES]
    if not out.strip() and proc.returncode == 0:
        return f"exit=0\n(command succeeded with no output)"
    return f"exit={proc.returncode}\n{out}"

def tool_git(sandbox: str, subcmd: str) -> str:
    """执行 git 命令,返回输出结果。"""
    allowed = {"status", "diff", "log", "branch", "remote"}
    #为了安全起见,只允许执行一些基本的 git 命令,避免潜在的破坏性操作。
    #log --oneline -n 5 表示显示最近 5 条提交记录的简洁格式,可以帮助了解代码的最新变化。
    if subcmd.split()[0] not in allowed:
        raise RuntimeError(f"git subcmd not allowed: {subcmd}")
    #subcmd.split()[0] 是为了获取 git 命令的第一个单词,即实际的子命令,比如 status、diff、log 等。通过检查这个子命令是否在 allowed 集合中,可以确保只执行被允许的 git 操作,从而降低安全风险。
    return tool_run_shell(sandbox, f"git {subcmd}")


TOOLS: dict[str, Callable[..., str]] = {
    "read_file": tool_read_file,
    "run_shell": tool_run_shell,
    "edit_file": tool_edit_file,
    "ripgrep": tool_ripgrep,
    "tree_sitter_symbols": tool_tree_sitter_symbols,
    "git": tool_git,
}


# ---------------------------------------------------------------------------
# stub model  --  deterministic script so loop is testable without LLM
# §14.01 agent-loop (ToyLLM pattern)
# ---------------------------------------------------------------------------

SCRIPT = [
    {"plan": [("locate target file", "in_progress"),
              ("read and diagnose", "pending"),
              ("apply fix and verify", "pending")],
     "tool": ("run_shell", {"cmd": "ls"}),
     "tokens": 1200, "cost": 0.02},
    {"plan": [("locate target file", "done"),
              ("read and diagnose", "in_progress"),
              ("apply fix and verify", "pending")],
     "tool": ("read_file", {"path": "README.md"}),
     "tokens": 900, "cost": 0.02},
    {"plan": [("locate target file", "done"),
              ("read and diagnose", "done"),
              ("apply fix and verify", "done")],
     "tool": None,  # terminal turn
     "tokens": 600, "cost": 0.01},
]


def model_step(plan: PlanState, turn: int,history: list[dict]) -> dict[str, Any]:
    """调用DEEPSEEK API 获取模型的回复，并解析成计划状态、工具调用、预算消耗等信息。"""
    #1. 通过summary方法获取当前计划状态的文本表示，并将其作为输入发送给DEEPSEEK API。
    plan_text = plan.summary()
    #2. 构造一个用户消息，包含当前任务、计划状态和当前轮数等信息，并将其作为输入发送给DEEPSEEK API。
    history_text = ""
    for h in history[-3:]:
        history_text += f"\ntool: {h.get('tool', 'unknown')}\nresult: {h.get('result', 'no result')}\n"
    user_msg = f"当前任务:{plan.goal}\n\n当前计划状态:\n{plan_text}\n\n最近历史:\n{history_text}\n\n这是第{turn + 1}轮，请根据上述信息生成下一步的计划和工具调用。"
    #3. 调用DEEPSEEK API，传入系统提示和用户消息，获取模型的回复.
    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
        try:
            stream = client.chat.completions.create(
                model = os.environ.get("MIMO_SB", "mimo-v2.5"),
                #读取环境变量 DEEPSEEK_FLASH_MODEL 的值作为模型名称，如果没有设置该环境变量，则使用默认值 "deepseek-v4-flash"。
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg}
                ],
                temperature = 0.1, 
                response_format = {"type": "json_object"},
                stream = True,
                timeout = 60,
            )
            break  # 成功则跳出重试循环
        except Exception as e:
            last_error = e
            print(f"  [API调用失败, 第{attempt+1}/{max_retries}次重试: {e}]")
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))  # 递增等待
            continue
    else:
        # 所有重试都失败
        raise RuntimeError(f"API调用在{max_retries}次重试后仍然失败: {last_error}")

    #4.解析模型的回复，提取计划状态、工具调用、预算消耗等信息，并返回一个字典对象。

    content = ""
    for chunk in stream:
        if not chunk.choices:  # 空 chunk 跳过
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            print(delta.content, end="", flush=True)
            content += delta.content
    print()  # 换行
    #通过迭代 stream 中的每个 chunk，获取模型回复的增量内容 delta.content，并将其累积到 content 字符串中。最终得到完整的模型回复文本 content。

    data = json.loads(content) 
    #data 是一个字典，表示解析后的 JSON 对象。通过 json.loads() 函数将 content 字符串解析成一个 Python 字典对象，这样就可以通过键来访问其中的计划状态、工具调用、预算消耗等信息了。

    # 5.把json对象中的 "plan" 字段转换成一个 TodoItem 列表，并提取工具调用的信息。
    items = [TodoItem(i + 1, desc, status) for i, (desc, status) in enumerate(data["plan"])]
    #根据模型回复中的 "plan" 字段，创建一个 TodoItem 列表。data["plan"] 是一个列表，每个元素是一个包含步骤描述和状态的二元组。通过 enumerate() 函数获取每个步骤的索引 i 和内容 (desc, status)，然后创建一个 TodoItem 对象，其中 id 是 i + 1（从 1 开始编号），description 是 desc，status 是 status。最终得到一个 TodoItem 的列表 items。

    tool = None
    if data.get("tool") and data.get("args"):
        tool = (data["tool"], data["args"])
    #从模型回复中提取工具调用的信息。如果模型回复中包含 "tool" 和 "args" 字段，并且它们都有值，那么就将它们作为一个元组 (data["tool"], data["args"]) 赋值给变量 tool。否则，tool 将保持为 None，表示没有工具调用。

    # 6.流式模式下 response.usage 不可用，用内容长度估算 token
    tokens = len(content) * 2  # 粗略估算：1个中文字约2个token
    cost = tokens * 0.000002

    return {"plan": items, "tool": tool, "tokens": tokens, "cost": cost}



# ---------------------------------------------------------------------------
# main loop  --  plan / act / observe / recover with full hook integration
# §14.01 agent-loop  §14.12 anthropic-workflow-patterns
# ---------------------------------------------------------------------------

def destructive_guard(payload: dict[str, Any]) -> dict[str, Any]:  # §14.27 prompt-injection-defense
    cmd = payload.get("args", {}).get("cmd", "")
    if "rm -rf" in cmd or "shutdown" in cmd:
        payload["blocked"] = True
        payload["reason"] = "destructive command blocked by PreToolUse hook"
    return payload


def run_agent(task: str, sandbox: str) -> dict[str, Any]:
    plan = PlanState(goal=task, items=[])
    budget = Budget()
    hooks = HookBus()
    trace: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []

    hooks.on("PreToolUse", destructive_guard)
    hooks.on("PostToolUse", lambda p: (trace.append({"event": "tool", **p}), p)[1])
    hooks.on("SessionStart", lambda p: (trace.append({"event": "start", **p}), p)[1])
    hooks.on("SessionEnd", lambda p: (trace.append({"event": "end", **p}), p)[1])
    #通过 hooks.on() 方法注册了多个事件的回调函数，这些函数会在相应的事件发生时被调用。每个回调函数都接受一个 payload 字典作为参数，并且通常会将一些信息添加到 trace 列表中，以便记录整个会话的过程和结果。
    #lambda p: (trace.append({"event": "tool", **p}), p)[1] 这个回调函数会在每次工具使用后被调用，它会将当前事件的相关信息（如工具名称、参数、结果等）添加到 trace 列表中，并且返回原始的 payload 以供后续处理。类似地，其他回调函数也会在会话开始和结束时记录相应的信息。

    def write_trace(payload: dict[str, Any]) -> dict[str, Any]:
        #路径被设置为 sandbox 的父目录下的 trace.json 文件，这样可以在沙箱外部查看和分析整个会话的事件记录。
        trace_path = os.path.join(sandbox, "..", "trace.json")
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(trace, f, indent=2, default=str)
        print(f"Trace written to {trace_path}")
        return payload

    hooks.on("Stop", write_trace)
    #当 "Stop" 事件被触发时，write_trace 函数会被调用，它会将 trace 列表中的事件记录写入到指定的 trace.json 文件中
    
    hooks.fire("SessionStart", {"task": task, "sandbox": sandbox,
                                "started_at": time.time()})
    #fire() 方法用于触发一个事件，并传递一个包含相关信息的字典作为 payload。在这里，当会话开始时，触发 "SessionStart" 事件，并传递一个包含任务描述、沙箱路径和开始时间的字典。注册在 "SessionStart" 事件上的回调函数将会被调用，并且可以使用这些信息来记录会话的开始状态。

    turn = 0
    call = None  # 初始化，避免预算超限时未定义
    while True:
        stop = budget.exceeded()
        if stop:
            hooks.fire("Stop", {"reason": stop, "turn": turn})
            break

        step = model_step(plan, turn, history)
        plan.items = step["plan"]
        budget.step(step["tokens"], step["cost"])

        call = step["tool"]
        if call is None:
            hooks.fire("Stop", {"reason": "complete", "turn": turn})
            break

        name, args = call
        pre = hooks.fire("PreToolUse", {"tool": name, "args": args})
        if pre.get("blocked"):
            hooks.fire("PostToolUse", {"tool": name, "blocked": True,
                                       "reason": pre.get("reason", "")})
            turn += 1
            continue

        try:
            result = TOOLS[name](sandbox, **args)
            hooks.fire("PostToolUse", {"tool": name, "ok": True,
                                       "bytes": len(result)})
            history.append({"tool": name, "args": args, "result": result})
        except Exception as exc:
            hooks.fire("PostToolUse", {"tool": name, "ok": False,
                                       "error": str(exc)})
            history.append({"tool": name, "args": args, "result": str(exc)})

        turn += 1
        #history 列表用于记录每一轮的工具调用信息，包括工具名称、参数和结果等。这些信息可以在后续的模型输入中提供给 LLM，以便它能够根据之前的操作和结果来调整计划和决策。

    hooks.fire("SessionEnd", {"turns": budget.turns_used,
                              "tokens": budget.tokens_used,
                              "dollars": budget.dollars_used})

    stop_reason = budget.exceeded()
    success = call is None and not stop_reason
    return {"plan": plan.summary(), "budget": asdict(budget), "trace": trace, "success": success}


def main() -> None:
    task = "demonstrate the plan-act-observe loop without network calls"
    with tempfile.TemporaryDirectory()as sandbox:
        result = run_agent(task, sandbox)
        print(result["plan"])
        print("---")
        print(f"turns={result['budget']['turns_used']} "
            f"tokens={result['budget']['tokens_used']} "
            f"dollars=${result['budget']['dollars_used']:.3f}")
        print("---")
        print(f"trace events: {len(result['trace'])}")
        for ev in result["trace"]:
            print(" ", json.dumps(ev, default=str))


if __name__ == "__main__":
    main()