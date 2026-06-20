"""测试者角色 — 运行测试，报告结果

测试者是多 Agent 团队的最后一道防线。它的工作是：
1. 读取评审者批准的代码
2. 在干净环境中运行测试
3. 报告通过或失败

设计原则：
- 测试者在干净沙箱中运行（不受编码者影响）
- 失败时要报告具体的堆栈跟踪
- 测试结果直接决定是否能开 PR
"""

from __future__ import annotations

from board import Board, Message, MsgKind
from roles.base import Role
import tempfile

TESTER_PROMPT = """你是一个测试工程师。你需要对提交的代码运行测试，并报告结果。

你会收到代码 diff 和测试用例。请分析代码是否能通过测试。

你必须严格以 JSON 格式回复：
{
  "passed": true 或 false,
  "test_results": "测试输出摘要",
  "coverage": "代码覆盖率估算（如 85%）",
  "issues": [
    {
      "test": "失败的测试名称",
      "error": "错误信息"
    }
  ]
}

重要规则：
- 仔细检查代码逻辑是否正确
- 如果测试会失败，passed 设为 false，并在 issues 中说明原因
- 如果所有测试会通过，passed 设为 true
"""


class Tester(Role):
    """测试者：运行测试 → 报告通过/失败
    
    工作流程：
    1. 从 Board 读取 APPROVED 消息
    2. 调用 LLM 分析代码是否能通过测试
    3. 发布 TEST_PASSED 或 TEST_FAILED 消息
    """


    def run(self, board: Board, diffs: list[dict] | None = None) -> bool:
        """运行测试者逻辑
        Args:
            board: 任务板
            diffs: 编码者的 diff 列表（可选，也可从 board 读取）           
        Returns:
            True 如果测试通过，False 如果失败
        """

        if diffs is None:
            test_msgs = board.inbox(self.name)
            if not test_msgs:
                raise ValueError(f"[{self.name}] 没有收到测试消息")
            latest_msg = test_msgs[-1]
            diffs = latest_msg.payload.get("diffs", [])


        code_summary = ""
        for i, diff in enumerate(diffs):
            code_summary += f"\n--- 文件 {i+1} ---\n"
            code_summary += f"\n子任务: {diff.get('subtask', 'unknown')}\n"
            for f in diff.get("files", []):
                code_summary += f"\n文件: {f.get('path', '?')}\n"
                code_summary += f.get("content", "")[:1500]
                code_summary += "\n"

        #构建用户信息，并获取LLM 的回复
        user_msg = f"请根据以下代码摘要判断是否能通过测试:\n{code_summary}"
        data = self.call_llm(TESTER_PROMPT, user_msg)

        #从LLM的回复提取信息   
        passed = data.get("passed", False)
        test_results = data.get("test_results", [])
        coverage = data.get("coverage", 0.0)
        issues = data.get("issues", [])

        #失败时将错误信息发送给第一个 coder
        if not passed:
            first_coder = diffs[0].get("coder", "coder-A") #怎么失败测试循环回拥有该子任务的编码者。
            board.post(Message(
                kind = MsgKind.TEST_FAILED,
                by = self.name,
                to = first_coder,
                payload = {"test_results": test_results, "coverage": coverage, "issues": issues},
                tokens = self.tokens_used
            ))
        else:
            board.post(Message(
            kind=MsgKind.TEST_PASSED,
            by=self.name,
            to="pr_opener",
            payload={"test_results": test_results, "coverage": coverage},
            tokens=self.tokens_used,
        ))
            
        return passed
    



