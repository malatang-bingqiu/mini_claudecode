# 新项目 README 模板

# <mini_claudecode>

<参考claudecode的coding agent，通过配置文件可以选择使用线上模型或者本地ollama模型>

## 快速开始

```bash
git clone <仓库地址>
cd <项目名>
pip install -r requirements.txt
export LLM_API_KEY=<你的 key>
python -m src.main
```

**三行以内必须能跑起来。** 需要 5 步以上才能跑的项目，说明它还没做完。

## 它现在能做什么

- [x] <已经能跑的功能>
- [ ] <还没做的>

## 架构

```
src/
  main.py        # 入口
  llm.py         # 模型调用封装
  ...
```

<一张简单的 ASCII 图或 mermaid 图：输入 → 处理 → 输出>

## 当前状态

- 里程碑：**L1**（能在自己电脑跑通）／ L2 / L3 / L4 / L5
- 上次更新：<日期>

## 已知问题

| 问题 | 打算怎么解 | 什么时候 |
|---|---|---|
| <模型偶尔返回空> | <加重试> | <这周> |

## 为什么这么设计

<写你的取舍：为什么不用框架、为什么选这个存储、哪条路试过但走不通。>

---

## 检查清单（推到 GitHub 之前）

- [ ] 第一屏有"解决什么问题"
- [ ] 有能在 3 行内跑起来的命令
- [ ] 有 `requirements.txt` 或 `pyproject.toml`
- [x] 有 `.gitignore`（至少忽略 `.env`、`__pycache__`、`*.pyc`）
- [x] **没有把 API key 提交上去**
- [ ] "当前状态"是真实的，不是愿望


