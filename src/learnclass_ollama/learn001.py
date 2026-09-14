# main.py
import os
import subprocess
from pathlib import Path
from ollama import chat
from config import OLLAMA_MODEL

WORKDIR = Path.cwd()

def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = (WORKDIR / path).resolve().read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} 行更多内容）"]
        return "\n".join(lines)
    except Exception as e:
        return f"错误：{e}"


def run_write(path: str, content: str) -> str:
    try:
        file_path = (WORKDIR / path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return f"已写入 {len(content)} 字节到 {path}"
    except Exception as e:
        return f"错误：{e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = (WORKDIR / path).resolve()
        text = file_path.read_text()
        if old_text not in text:
            return f"错误：在文件中未找到目标文本：{path}"
        file_path.write_text(text.replace(old_text, new_text, 1))
        return f"已编辑 {path}"
    except Exception as e:
        return f"错误：{e}"


def run_glob(pattern: str) -> str:
    import glob as g
    try:
        results = []
        for match in g.glob(pattern, root_dir=WORKDIR):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "（无匹配）"
    except Exception as e:
        return f"错误：{e}"

# ── 工具执行 powershell────────────────────────────────────────
def run_bash(command: str) -> str:
    # 与check_deny_list重复
    # dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/",
    #              "format ", "del /f /s /q", "rd /s /q"]
    # if any(d in command for d in dangerous):
    #     return "错误：危险命令已被拦截"
    try:
        r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         f"[Console]::OutputEncoding=[Text.Encoding]::UTF8; {command}"],
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
TOOLS_Anthropic = [
    {"name": "bash", "description": "运行一条 shell 命令。",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "读取文件内容。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "向文件写入内容。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "在文件中替换一次完全匹配的文本。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "查找匹配 glob 模式的文件。",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]

def to_ollama_tools(tools):
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]

# 用法
ollama_tools = to_ollama_tools(TOOLS_Anthropic)

TOOL_HANDLERS = {
    "bash": run_bash, "read_file": run_read, "write_file": run_write,
    "edit_file": run_edit, "glob": run_glob,
}

# 关卡 1：硬性拒绝列表 — 始终禁止
DENY_LIST = [
    # Linux 风格
    "rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if=", "> /dev/sda",
    # Windows 风格
    "rmdir /s", "rd /s", "del /f", "del /s", "format ",
    "Remove-Item -Recurse", "Remove-Item -Force",
    # 通用高危路径
    "C:\\Windows", "D:\\Users", "C:\\Users", "System32",
]

def check_deny_list(command: str) -> str | None:
    for pattern in DENY_LIST:
        if pattern in command:
            return f"已拦截：'{pattern}' 位于拒绝列表中"
    return None


# 关卡 2：规则匹配 — 根据上下文检查
PERMISSION_RULES = [
    {"tools": ["read_file", "write_file", "edit_file"],
     "check": lambda args: not (WORKDIR / args.get("path", "")).resolve().is_relative_to(WORKDIR),
     "message": "写入工作区外部路径"},
    {"tools": ["bash"],
     "check": lambda args: any(kw in args.get("command", "") for kw in ["rm ", "rmdir", "rd ", "del ", "remove-item", "> /etc/", "chmod 777", "format"]),
     "message": "可能具有破坏性的命令"},
]

def check_rules(tool_name: str, args: dict) -> str | None:
    for rule in PERMISSION_RULES:
        if tool_name in rule["tools"] and rule["check"](args):
            return rule["message"]
    return


# 关卡 3：用户审批 — 规则命中后等待确认
def ask_user(tool_name: str, args: dict, reason: str) -> str:
    print(f"\n\033[33m⚠  {reason}\033[0m")
    print(f"   工具：{tool_name}({args})")
    choice = input("   是否允许？[y/N] ").strip().lower()
    return "allow" if choice in ("y", "yes") else "deny"


# 流水线：三道关卡串联

def check_permission(tool_name: str, args: dict) -> bool:
    # 关卡 1：硬性拒绝列表
    if tool_name == "bash":
        reason = check_deny_list(args.get("command", ""))
        if reason:
            print(f"\n\033[31m⛔ {reason}\033[0m")
            return False

    # 关卡 2：规则匹配
    reason = check_rules(tool_name, args)
    if reason:
        # 关卡 3：用户审批
        decision = ask_user(tool_name, args, reason)
        if decision == "deny":
            return False

    return True


def run_agent(user_input: str, messages: list) -> str:
    """跑一轮完整的工具调用循环，返回最终回复"""
    messages.append({"role": "user", "content": user_input})

    while True:
        response = chat(
            model=OLLAMA_MODEL,
            messages=messages,
            tools=ollama_tools,
        )
        messages.append(response.message)

        # 没有工具调用 → 说明模型给出最终答案
        if not response.message.tool_calls:
            return response.message.content
       

        # 处理工具调用
        # 判断消息中是否有tool_calls，以判断工具是否被调用
        print(f"\n调用工具前：\n{response.message}\n{'***'*10}")

        # 有工具调用 → 逐个执行
        for tc in response.message.tool_calls:
            name = tc.function.name
            args = tc.function.arguments or {}
            print(f"  [调用工具] {name}({args})")

            # ── 三道权限关卡 ──
            if not check_permission(name, args):
                result = "权限被拒绝。"
                print(f"  [已拒绝] {name}")
            else:
                handler = TOOL_HANDLERS.get(name)
                if handler is None:
                    result = f"未知工具：{name}"
                else:
                    result = handler(**args)
                print(f"  [工具返回] {result}")

            # 每个工具结果单独作为一条 tool 消息追加
            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": str(result),
            })
        print("---"*10)


def main():
    messages = [{
        "role": "system",
        "content": f"你是一个个人助手。你可以合理调用tool来满足用户需求，不要编造。你的工作目录在{WORKDIR}"
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
        print("==="*10)


if __name__ == "__main__":
    main()