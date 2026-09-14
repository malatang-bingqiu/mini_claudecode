import os
import subprocess
from pathlib import Path
from ollama import chat
from config import OLLAMA_MODEL

WORKDIR = Path.cwd()

def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"路径逃逸出工作区：{p}")
    return path

def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} 行更多内容）"]
        return "\n".join(lines)
    except Exception as e:
        return f"错误：{e}"


def run_write(path: str, content: str) -> str:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return f"已写入 {len(content)} 字节到 {path}"
    except Exception as e:
        return f"错误：{e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path)
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

# ═══════════════════════════════════════════════════════════
#  新增于 s04: 钩子系统（s03 权限逻辑现在通过钩子实现）
# ═══════════════════════════════════════════════════════════

HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}

def register_hook(event: str, callback):
    HOOKS[event].append(callback)

def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:  # 教学快捷方式：拦截这个工具调用
            return result
    return None

## s03 权限检查逻辑，现在封装成钩子
DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]

def permission_hook(block):
    """PreToolUse：这里承载从 s03 迁移过来的 check_permission() 逻辑。"""
    if block.name == "bash":
        for pattern in DENY_LIST:
            if pattern in block.arguments.get("command", ""):
                print(f"\n\033[31m⛔ 已拦截：'{pattern}'\033[0m")
                return "被拒绝列表拒绝授权"
        for kw in DESTRUCTIVE:
            if kw in block.arguments.get("command", ""):
                print(f"\n\033[33m⚠  可能具有破坏性的命令\033[0m")
                print(f"   工具：{block.name}({block.arguments})")
                choice = input("   是否允许？[y/N] ").strip().lower()
                if choice not in ("y", "yes"):
                    return "用户拒绝授权"
    if block.name in ("read_file", "write_file", "edit_file"):
        path = block.arguments.get("path", "")
        if not (WORKDIR / path).resolve().is_relative_to(WORKDIR):
            print(f"\n\033[33m⚠  访问工作区外部路径\033[0m")
            print(f"   工具：{block.name}({block.arguments})")
            choice = input("   是否允许？[y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "用户拒绝授权"
    return None

def log_hook(block):
    """PreToolUse：记录每一次工具调用。"""
    args = block.arguments or {}
    preview_parts = []
    for k, v in list(args.items())[:2]:
        v_str = str(v)
        if len(v_str) > 40:
            v_str = v_str[:40] + "..."
        preview_parts.append(f"{k}={v_str!r}")
    preview = ", ".join(preview_parts)
    print(f"\033[90m[钩子] {block.name}({preview})\033[0m")
    return None

def large_output_hook(block, output):
    """PostToolUse：对大型输出给出提醒。"""
    if len(str(output)) > 100000:
        print(f"\033[33m[钩子] ⚠ 来自以下工具的大输出：{block.name}: {len(str(output))} 个字符\033[0m")
    return None

# 用户提交提示词钩子：在用户输入到达 LLM 前记录它
def context_inject_hook(query: str):
    print(f"\033[90m[钩子] UserPromptSubmit: 工作目录：{WORKDIR}\033[0m")
    return None

# 停止钩子：在循环即将退出时打印摘要
def summary_hook(messages: list):
    tool_count = sum(1 for m in messages if m.get("role") == "tool")
    print(f"\033[90m[钩子] Stop：会话使用了 {tool_count} 次工具调用\033[0m")
    return None

register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)

def agent_loop(user_input: str, messages: list) -> str:
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
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({
                    "role": "assistant",
                    "content": force})
                continue
            return response.message.content

        # 处理工具调用
        # 判断消息中是否有tool_calls，以判断工具是否被调用
        # print(f"\n调用工具前：\n{response.message}\n{'***'*10}")

        # 有工具调用 → 逐个执行
        for tc in response.message.tool_calls:
            name = tc.function.name
            args = tc.function.arguments or {}
            # print(f"  [调用工具] {name}({args})")

            # s04 变化： Hook 替代硬编码的 check_permission()
            blocked = trigger_hooks("PreToolUse", tc.function)
            if blocked:
                messages.append({"role": "tool", "tool_name": name, "content": str(blocked),})
                continue
            handler = TOOL_HANDLERS.get(name)
            result = handler(**args) if handler is not None else f"未知工具：{name}"
            trigger_hooks("PostToolUse", tc.function, result)  # s04: 后置钩子
            messages.append({"role": "tool", "tool_name": name, "content": str(result),})
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
        trigger_hooks("UserPromptSubmit", user_input)
        reply = agent_loop(user_input, messages)
        print(f"\n助手: {reply}\n")
        print("==="*10)


if __name__ == "__main__":
    main()