# main.py
import os
import subprocess
from ollama import chat
from config import OLLAMA_MODEL

# todo: 第一步：定义工具函数
def add(a: int, b: int) -> int:
    """
    将数字a与数字b相加
    Args:
        a: 第一个数字
        b: 第二个数字
    """
    return a + b


def multiply(a: int, b: int) -> int:
    """
    将数字a与数字b相乘
    Args:
        a: 第一个数字
        b: 第二个数字
    """
    return a * b

# ── 工具执行 cmd.exe────────────────────────────────────────
# def run_bash(command: str) -> str:
#     dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
#     if any(d in command for d in dangerous):
#         return "错误：危险命令已被拦截"
#     try:
#         r = subprocess.run(command, shell=True, cwd=os.getcwd(),
#                            capture_output=True, text=True, timeout=120)
#         out = (r.stdout + r.stderr).strip()
#         return out[:50000] if out else "（无输出）"
#     except subprocess.TimeoutExpired:
#         return "错误：执行超时（120 秒）"
#     except (FileNotFoundError, OSError) as e:
#         return f"错误：{e}"

# ── 工具执行 powershell────────────────────────────────────────
def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/",
                 "format ", "del /f /s /q", "rd /s /q"]
    if any(d in command for d in dangerous):
        return "错误：危险命令已被拦截"
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=120,
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "（无输出）"
    except subprocess.TimeoutExpired:
        return "错误：执行超时（120 秒）"
    except (FileNotFoundError, OSError) as e:
        return f"错误：{e}"   

# 定义 JSON 格式的工具 schema
tools = [
    {
        "type": "function",
        "function": {
            "name": "add",
            "description": "将数字a与数字b相加",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "integer",
                        "description": "第一个数字"
                    },
                    "b": {
                        "type": "integer",
                        "description": "第二个数字"
                    }
                },
                "required": ["a", "b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "multiply",
            "description": "将数字a与数字b相乘",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "integer",
                        "description": "第一个数字"
                    },
                    "b": {
                        "type": "integer",
                        "description": "第二个数字"
                    }
                },
                "required": ["a", "b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "运行一条 shell 命令",
            "parameters": {
                "type": "object",
                "properties": {
                    "properties": {"command": {"type": "string"}},
                },
                "required": ["command"],
            }
        }
    }
]

mytools = {"add": add, "multiply": multiply, "run_bash": run_bash}

def run_agent(user_input: str, messages: list) -> str:
    """跑一轮完整的工具调用循环，返回最终回复"""
    messages.append({"role": "user", "content": user_input})

    while True:
        response = chat(
            model=OLLAMA_MODEL,
            messages=messages,
            tools=tools,
        )
        messages.append(response.message)

        # 没有工具调用 → 说明模型给出最终答案
        if not response.message.tool_calls:
            return response.message.content
       

        # 处理工具调用
        # 判断消息中是否有tool_calls，以判断工具是否被调用
        print(f"\n调用工具前：\n{response.message}")

                # 有工具调用 → 逐个执行，把结果塞回对话
        for tc in response.message.tool_calls:
            name = tc.function.name
            args = tc.function.arguments or {}
            print(f"  [调用工具] {name}({args})")

            selected_tool = mytools[name]
            result = selected_tool(**args)
            print(f"  [工具返回] {result}")

            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": str(result),   # 已经是字符串了
            })


def main():
    messages = [{
        "role": "system",
        "content": f"你是一个个人助手。你可以合理调用tool来满足用户需求，不要编造。你的工作目录在{os.getcwd()}"
    }]

    print("个人助手已启动（输入 exit 退出）\n")
    while True:
        user_input = input("你: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue

        reply = run_agent(user_input, messages)
        print(f"\n助手: {reply}\n")


if __name__ == "__main__":
    main()