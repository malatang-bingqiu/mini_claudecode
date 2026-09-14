# main.py
import json
from ollama import chat

from learn001.config import OLLAMA_MODEL
from learn001.tools import get_tool_schemas, call_tool


def run_agent(user_input: str, messages: list) -> str:
    """跑一轮完整的工具调用循环，返回最终回复"""
    messages.append({"role": "user", "content": user_input})

    while True:
        response = chat(
            model=OLLAMA_MODEL,
            messages=messages,
            tools=get_tool_schemas(),
        )
        messages.append(response.message)

        # 没有工具调用 → 说明模型给出最终答案
        if not response.message.tool_calls:
            return response.message.content

        # 有工具调用 → 逐个执行，把结果塞回对话
        for tc in response.message.tool_calls:
            name = tc.function.name
            args = tc.function.arguments or {}
            print(f"  [调用工具] {name}({args})")

            result = call_tool(name, args)
            print(f"  [工具返回] {result}")

            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": result,   # 已经是字符串了
            })


def main():
    messages = [{
        "role": "system",
        "content": "你是一个个人助手。当用户询问位置相关问题时，调用 get_current_location 获取真实位置，不要编造。"
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