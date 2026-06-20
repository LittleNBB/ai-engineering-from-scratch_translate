"""Multi-agent software team — typed task board + handoff accounting scaffold.

The hard architectural primitive is the typed message task board that
coordinates an architect, N parallel coders, a reviewer, and a tester, with
every role boundary producing a trace span. This scaffold runs the full
message flow with stubbed LLM calls so the handoff logic and token accounting
are observable end to end.

Run:  python main.py
"""

from __future__ import annotations

import random

from roles import Architect, Coder, Reviewer, Tester
from board import Board, MsgKind, Message as Msg, Subtask
from config import client, DEFAULT_MODEL






# ---------------------------------------------------------------------------
# orchestrator  --  runs the full flow, computes token amplification
# ---------------------------------------------------------------------------

def run_team(issue: str, n_coders: int = 4, rng: random.Random | None = None) -> dict:
    #实例化
    board = Board()
    architect = Architect(name="architect", model=DEFAULT_MODEL, client=client)
    reviewer = Reviewer(name="reviewer", model=DEFAULT_MODEL, client=client)
    tester = Tester(name="tester", model=DEFAULT_MODEL, client=client)

    # architect
    # 在 architect.run() 之前，先发一条消息给架构师
    board.post(Msg(
        kind=MsgKind.PLAN_REQUEST,
        by="orchestrator",
        to="architect",
        payload={"issue": issue},
    ))
    plan = architect.run(board=board)

    # dispatch subtasks to coders
    for i, sub in enumerate(plan[:n_coders]):
        coder_name = f"coder-{chr(65 + i)}"

        board.post(Msg(MsgKind.SUBTASK, by="architect", to=coder_name,
                       payload={"subtask": sub.name, "files": sub.files},
                       tokens=1200))

    # coders implement in parallel
    diffs: list[dict] = []
    for i, sub in enumerate(plan[:n_coders]):
        coder_name = f"coder-{chr(65 + i)}"
        coder = Coder(name=coder_name, model=DEFAULT_MODEL, client=client) # 在循环中为每一个coder实例化
        result = coder.run(board=board, subtask=sub) 
        diffs.append(result)

    coder_tokens = sum(v for k, v in board.token_by_role.items() if k.startswith("coder"))
    amplification = board.total_tokens() / max(1, coder_tokens)

    # reviewer
    
    # 合并协调：把所有 diff 拼成一个列表（编排器直接处理，不需要单独角色）
    board.post(Msg(
        kind=MsgKind.REVIEW_NEEDED,
        by="orchestrator",
        to="reviewer",
        payload={"diffs": diffs},
    ))

    review = reviewer.run(board=board)

    # tester — 直接传入 diffs，不依赖 board 消息
    passed = tester.run(board=board, diffs=diffs)


    # 如果测试通过，模拟开 PR
    if passed:
        print(f"[pr] ✅ 测试通过，准备开 PR（模拟）")

    return {
        "approved": bool(review),
        "review_comment": "ok" if review else "rejected",
        "tested_passed": passed,
        "test_msg": "passed" if passed else "failed",
        "total_tokens": board.total_tokens(),
        "tokens_by_role": dict(board.token_by_role),
        "token_amplification": amplification,
        "handoffs": sum(1 for m in board.message if m.to != m.by),
        "handoff_log":board.handoffs
    }


# ---------------------------------------------------------------------------
# run several matched trials vs single-agent baseline
# ---------------------------------------------------------------------------

def single_agent_baseline(issue: str, rng: random.Random) -> dict:
    """Stub: one Sonnet 4.7 in a single worktree does the whole thing."""
    # slower but fewer handoffs; tokens roughly the whole budget minus role overhead
    return {
        "passed": rng.random() < 0.68,
        "total_tokens": 18_000 + rng.randint(0, 6_000),
    }


def main() -> None:
    print("=== multi-agent team run ===")
    result = run_team("fix widget parser race", n_coders=3)
    print(f"approved     : {result['approved']}  ({result['review_comment']})")
    print(f"tested passed: {result['tested_passed']}  ({result['test_msg']})")
    print(f"handoffs     : {result['handoffs']}")
    print(f"total tokens : {result['total_tokens']:,}")
    print("tokens by role:")
    for role, n in sorted(result['tokens_by_role'].items(), key=lambda x: -x[1]):
        print(f"  {role:14s} {n:>6,}")
    print(f"token amplification: {result['token_amplification']:.2f}x")
    for h in result['handoff_log']:
        print(f"  {h['from']:>14s} → {h['to']:<14s}  {h['kind']:20s}  {h['tokens']:>5} tok  {h['payload_size']:>4} B")


if __name__ == "__main__":
    main()
