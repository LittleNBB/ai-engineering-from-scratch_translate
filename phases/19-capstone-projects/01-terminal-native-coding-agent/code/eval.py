import json
import os
import sys
import time
import tempfile


sys.path.insert(0,os.path.dirname(__file__))
from main import run_agent, load_dotenv

load_dotenv()


# write 10 test cases
TASKS = [
    "列出当前目录下的全部文件",
    "创建一个 hello.txt 文件，内容是 hello world",
    "读取 hello.txt 的内容",
    "创建一个 math.py 文件，定义一个 add 函数",
    "搜索 math.py 里的函数定义",
    "查看 git status",
    "在 hello.txt 末尾追加一行 goodbye",
    "创建一个 data.txt,写入 1 到 10",
    "读取 math.py 的内容",
    "删除 hello.txt",
]

def evaluate():
    results = []
    for i, task in enumerate(TASKS):
        print(f"\n{'='*50}")
        print(f"Task{i+1}/{len(TASKS)}: {task}")
        print(f"{'='*50}")
        #这三个print是为了让用户更清楚地看到当前的任务和分割线，增加可读性

        start = time.time()
        with tempfile.TemporaryDirectory() as sandbox:
            try:
                result = run_agent(task, sandbox)
                elapsed = time.time() - start
                entry = {
                    "task": task,
                    "turn": result["budget"]["turns_used"],
                    "tokens": result["budget"]["tokens_used"],
                    "dollar": result["budget"]["dollars_used"],
                    "seconds": round(elapsed, 1),#保留一位小数
                    "events": len(result["trace"]),#记录事件的数量
                    "success": result["success"],
                }

            except Exception as e:
                elapsed = time.time() - start#如果发生异常，记录下异常信息和时间,time.time() - start 计算从开始到异常发生的时间
                entry = {
                    "task": task,
                    "error": str(e),
                    "seconds": round(elapsed, 1),
                    "success": False,
                }

        results.append(entry)
        print(f"\nResult:{json.dumps(entry, ensure_ascii=False, indent=2)}")#打印结果，json.dumps 将 entry 转换为 JSON 格式的字符串，ensure_ascii=False 允许中文正常显示，indent=2 使输出更美观

        output_path = os.path.join(os.path.dirname(__file__), "eval_results.json")
        with open(output_path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")#将结果写入 eval_results.json 文件，每行一个 JSON 对象

    # 最终汇总
    print(f"\n{'='*50}")
    print(f"Summary:")
    success = [r for r in results if r.get("success")]
    print(f"Success: {len(success)}/{len(results)}")
    if success:
        avg_turn = sum(r["turn"] for r in success) / len(success)
        avg_tokens = sum(r["tokens"] for r in success) / len(success)
        avg_dollar = sum(r["dollar"] for r in success) / len(success)
        avg_seconds = sum(r["seconds"] for r in success) / len(success)
        print(f"Average Turn: {avg_turn:.1f}")
        print(f"Average Tokens: {avg_tokens:.1f}")
        print(f"Average Dollar: ${avg_dollar:.4f}")
        print(f"Average Seconds: {avg_seconds:.1f}")
    output_path = os.path.join(os.path.dirname(__file__), "eval_results.json")
    print(f"Results saved to {output_path}")

if __name__ == "__main__":
    evaluate()