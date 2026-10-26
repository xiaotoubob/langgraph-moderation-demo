# Learning progress

## 用户确认的旧进度

- 本地较小 Qwen3.5 跑通过 demo，使用简单 LangGraph 和 3–4 个工具。
- 已学习 checkpoint，准备系统学习 RAG；evaluation 计划在后续。

这些是用户提供的学习事实，不是本次云端复现的运行证据。

## 用户提供的找回记录

- State：messages、status、result、model_calls。
- draft → revise、部分状态更新、add_messages、普通 result 覆盖。
- 示例：AIMessage(content="Draft: checking the case.", id="answer-1")。
- checkpoint 保存各阶段；讨论过 messages/result 的用途区别。

旧工具名、目录、推理服务、checkpointer 和 time travel 学习情况未知。
SQLite、当前工具/schema/目录/phase 编号是新设计。

## 本次重建

- Phase 0–4 教学代码：3 条 policy、12 个案例、3 个工具、显式 graph、强制校验。
- scripted 回放人工答案，不是分类器，不能报告模型准确率。
- local 连接实际配置的 OpenAI-compatible 服务，不自动安装推理后端或下载模型。
- SQLite 历史、隔离、暂停、跨进程恢复；独立 reducer lab。
- 尚未实现 embedding/向量索引、agentic retrieval、evaluation、改进实验。

## 已验证的程序能力

执行位置为云端 Debian、Python 3.12，不是用户 WSL。

- 离线案例回放：工具请求/响应、三类结果契约、强制原文与引用校验。
- 错误路径：虚构证据、错误条款/版本/引用、格式修复、参数错误、调用预算。
- Checkpoint：SQLite 重开；独立进程 pause/resume；thread 隔离；早期状态保留。
- Reducer：同 ID 消息替换、普通字段覆盖、省略字段保留。
- 真实 ChatOpenAI SDK 对本地 HTTP stub：发送工具 schema，接收请求，返回 ToolMessage。
- 校验局限：真实但不支持结论的引用仍需人工/后续评估。

本次验证命令与结果：

- `uv sync --frozen --all-groups`：锁定依赖安装/重复执行通过。
- `ruff check .`、`ruff format --check .`：通过。
- `pytest -q`：37 passed，包括独立进程恢复与 HTTP stub；不是 37 个真实模型判例。
- README 中的离线 run、pause/history/resume、lab 命令：实际运行通过。
- wheel 构建及独立目录安装：3 条 policy 和 12 个案例均可加载。

这些结果对应当前云端代码版本，不代表 WSL、真实 Qwen 或新 cloud task 已验证。

## 尚未验证

- WSL 路径、Windows App 同 checkout、GPU 可用显存、已有推理服务。
- 真实 Qwen 的加载、量化、上下文、延迟、JSON、工具调用表现。
- 模型的分类质量、引用支持性、例外处理、抗 prompt injection 能力。
- 用户是否同意全部教学规则与人工答案；对新代码的理解程度。

## 下一 session

1. WSL 已 clone 仓库拉取提交，读 AGENTS/README/roadmap/本文件。
2. 只读检查本地环境、模型服务，避免重复下载或预设后端。
3. 离线演示和 checkpoint lab，简短复习 State/消息配对。
4. 配置真实模型，先基础 JSON、单次工具，再代表案例，记录失败。
5. 分开记录已运行、格式有效、判断质量、本人理解。
6. baseline 端到端验证后进入 Phase 5 固定检索。
