import sys
import os

# 把 code/ 目录加入 Python 搜索路径，这样才能 import main
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import destructive_guard

# 测试：rm -rf 应该被拦截
payload = {"args": {"cmd": "rm -rf /"}}
result = destructive_guard(payload)
assert result.get("blocked") == True

# 测试：普通命令不应该被拦截
payload = {"args": {"cmd": "ls"}}
result = destructive_guard(payload)
assert "blocked" not in result

print("✅ destructive_guard 测试通过")