import ast, json, os, subprocess, yaml
from pathlib import Path
from ollama import chat
from config import OLLAMA_MODEL

WORKDIR = Path.cwd()
SKILLS_DIR = WORKDIR / "skills"
CURRENT_TODOS: list[dict] = []


# s07: 技能目录扫描 (供下方 build_system 使用)
def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 SKILL.md 的 YAML frontmatter，返回 (meta, body)。"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, parts[2].strip()

# 启动时构建技能注册表 (用于在 load_skill 中安全查找)
SKILL_REGISTRY: dict[str, dict] = {}

def _scan_skills():
    """扫描 skills/ 目录，把名称、描述和内容写入 SKILL_REGISTRY。"""
    if not SKILLS_DIR.exists():
        return
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir():
            continue
        manifest = d / "SKILL.md"
        if manifest.exists():
            raw = manifest.read_text()
            meta, body = _parse_frontmatter(raw)
            name = meta.get("name", d.name)
            desc = meta.get("description", raw.split("\n")[0].lstrip("#").strip())
            SKILL_REGISTRY[name] = {"name": name, "description": desc, "content": raw}

_scan_skills()

def list_skills() -> str:
    """列出所有技能：名称 + 单行描述。"""
    if not SKILL_REGISTRY:
        return "（未找到技能）"
    return "\n".join(f"- **{s['name']}**: {s['description']}" for s in SKILL_REGISTRY.values())

# s07: SYSTEM 包含技能目录 (成本低 — 只有名称和描述)
def build_system() -> str:
    """构建 SYSTEM 提示词，并注入启动时扫描到的技能目录。"""
    catalog = list_skills()
    return (
        f"你是位于 {WORKDIR}. "
        f"可用技能：\n{catalog}\n"
        "需要时使用 load_skill 获取完整详情。"
    )

def load_skill(name: str) -> str:
    """通过注册表加载完整技能内容，避免路径穿越。"""
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        return f"未找到技能：{name}"
    return skill["content"]

SYSTEM = build_system()

# SYSTEM = (
#     f"你是位于 {WORKDIR}. "
#     "遇到复杂子问题时，使用 task 工具启动一个子 Agent。"
# )

SUB_SYSTEM = (
    f"你是位于 {WORKDIR}. "
    "完成交给你的任务，然后返回简洁摘要。"
    "不要继续委派。"
)


def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"路径逃逸出工作区：{p}")
    return path

def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(path).read_text(encoding='utf-8').splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} 行更多内容）"]
        return "\n".join(lines)
    except Exception as e:
        return f"错误：{e}"


def run_write(path: str, content: str) -> str:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
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

def _normalize_todos(todos):
    if isinstance(todos, str):
        try:
            todo_list = json.loads(todos)
        except json.JSONDecodeError:
            try:
                todo_list = ast.literal_eval(todos)
            except (SyntaxError, ValueError):
                return None, "错误：todos 必须是列表或 JSON 数组字符串"
    elif isinstance(todos, list):
        todo_list = todos
    else:
        return None, "错误：todos 必须是列表"
    for i, t in enumerate(todos):
        if not isinstance(t, dict):
            return None, f"错误：todos[{i}] 必须是对象"
        if "content" not in t or "status" not in t:
            return None, f"错误：todos[{i}] 缺少 'content' 或 'status'"
        if t["status"] not in ("pending", "in_progress", "completed"):
            return None, f"错误：todos[{i}] 包含无效状态 '{t['status']}'"
    return todo_list, None

def run_todo_write(todos: list) -> str:
    global CURRENT_TODOS
    todo_list, error = _normalize_todos(todos)
    if error:
        return error
    CURRENT_TODOS = todo_list
    lines = ["\n\033[33m## 当前任务\033[0m"]
    for t in CURRENT_TODOS:
        icon = {"pending": " ", "in_progress": "\033[36m▸\033[0m", "completed": "\033[32m✓\033[0m"}[t["status"]]
        lines.append(f"  [{icon}] {t['content']}")
    print("\n".join(lines))
    return f"已更新 {len(CURRENT_TODOS)} 个任务"

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
    {"name": "todo_write", "description": "为当前编码会话创建并维护任务清单。",
     "input_schema": {"type": "object", "properties": {"todos": {"type": "array", "items": {"type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}}, "required": ["content", "status"]}}}, "required": ["todos"]}},
    {"name": "task", "description": "启动一个子 Agent 处理复杂子任务。只返回最终结论。",
     "input_schema": {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"]}},
    # s07: 技能工具 (目录已在 SYSTEM 提示词中，此处加载完整内容)
    {"name": "load_skill", "description": "按名称加载某个技能的完整内容。",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
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


SUB_TOOLS = [
    {"name": "bash", "description": "运行一条 shell 命令。",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "读取文件内容。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "向文件写入内容。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "在文件中替换一次完全匹配的文本。",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "查找匹配 glob 模式的文件。",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]
# 没有 "task" 工具 — 防止递归启动

SUB_HANDLERS = {
    "bash": run_bash, "read_file": run_read, "write_file": run_write,
    "edit_file": run_edit, "glob": run_glob,
}

def extract_text(content) -> str:
    """从消息内容块中提取文本。"""
    if not isinstance(content, list):
        return str(content)
    return "\n".join(getattr(b, "text", "") for b in content if getattr(b, "type", None) == "text")

def spawn_subagent(description: str) -> str:
    """用全新的 messages[] 启动子 Agent，只返回摘要。"""
    print(f"\n\033[35m[子 Agent 已启动]\033[0m")
    messages = [{"role": "system","content": f"{SUB_SYSTEM}"}]
    messages.append({"role": "user", "content": description})  # 全新上下文

    for _ in range(30):  # 安全上限
        response = chat(model=OLLAMA_MODEL, messages=messages, tools=ollama_sub_tools,)
        messages.append(response.message)
        if not response.message.tool_calls:
            break
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
            print(f"Sub Tool result：{result}\n")
            trigger_hooks("PostToolUse", tc.function, result)  # s04: 后置钩子

            messages.append({"role": "tool", "tool_name": name, "content": str(result),})

    # 问题 5：如果在 tool_use 期间触发安全上限，则使用兜底逻辑
    result = extract_text(messages[-1]["content"])
    if not result:
        # 最后一条消息是 tool_result，向前查找 assistant 文本
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                result = extract_text(msg["content"])
                if result:
                    break
        if not result:
            result = "子 Agent 已等待 30 轮仍未给出最终回答，已停止。"
    print(f"\033[35m[子 Agent 已完成]\033[0m")
    return result  # 只保留摘要，完整消息历史会被丢弃

TOOL_HANDLERS = {
    "bash": run_bash, "read_file": run_read, "write_file": run_write,
    "edit_file": run_edit, "glob": run_glob, "todo_write": run_todo_write,
    "task": spawn_subagent, "load_skill": load_skill,
}

# 把 task 工具加入父 Agent 的工具列表
TOOLS_Anthropic.append({
    "name": "task",
    "description": "启动一个子 Agent 处理复杂子任务。只返回最终结论。",
    "input_schema": {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"]},
})
TOOL_HANDLERS["task"] = spawn_subagent



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

ollama_tools = to_ollama_tools(TOOLS_Anthropic)
ollama_sub_tools = to_ollama_tools(SUB_TOOLS)

def agent_loop(user_input: str, messages: list) -> str:
    """跑一轮完整的工具调用循环，返回最终回复"""
    messages.append({"role": "user", "content": user_input})
    rounds_since_todo = 0
    while True:
        # s05: 催办提醒 — 如果模型连续 3 轮没有更新待办，则注入提醒
        if rounds_since_todo >= 3 and messages:
            messages.append({"role": "user",
                             "content": "<reminder>请更新你的待办事项。</reminder>"})
            rounds_since_todo = 0

        response = chat(model=OLLAMA_MODEL, messages=messages, tools=ollama_tools,)
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
        rounds_since_todo += 1
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
            # print(f"Tool result：{result}\n")
            trigger_hooks("PostToolUse", tc.function, result)  # s04: 后置钩子
            if name == "todo_write":
                rounds_since_todo = 0
            messages.append({"role": "tool", "tool_name": name, "content": str(result),})
        print("---"*10)


def main():
    messages = [{
        "role": "system",
        "content": f"{SYSTEM}"
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