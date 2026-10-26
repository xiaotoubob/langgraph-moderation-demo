# Project and teaching agreement

这是个人 LangGraph 学习项目，通过教学用 Trust & Safety 内容审核理解 agentic workflow。
用中文解释，保留必要英文术语；优先采用小而可观察的实现。

## Start each session

1. 阅读 README.md、roadmap.md 和 learning-progress.md，再检查 Git 工作区。
2. 确认实际执行环境。云端、Windows、WSL 不能视为同一台机器；不推测本机路径、GPU 或推理服务。
3. 使用现有 checkout。每个 cloud task 已隔离，除非用户要求，不创建 Git worktree。
4. 聚焦用户指定的 phase；默认下一步是 WSL 本地模型验证，之后才进入 Phase 5。

## Historical facts versus new designs

- 用户确认旧项目跑通过较小 Qwen3.5、简单 LangGraph、3–4 个工具，已学过 checkpoint。
- 找回记录支持 messages/status/result/model_calls、draft → revise、add_messages、部分更新和字段覆盖。
- 旧目录、工具名、checkpointer、推理服务和 time travel 学习情况未确认。
- 当前代码是新重建；SQLite、工具名、schema、目录和 phase 编号不是找回的历史实现。

## Scope and correctness

- Phase 0–4 是本轮 baseline。不要顺手实现向量 RAG、reranker、evaluation 或 Web UI。
- input evidence 来自提交文本；policy citation 保留 ID、section 和 version。
- check_result 是最终结果必经的程序检查，不能让模型选择是否调用。
- 字面引用真实不等于语义支持；不要把存在性检查说成准确性评估。
- scripted 回放人工参考结果，只测试编排，不代表 Qwen、分类质量或对抗鲁棒性测试。
- 执行失败使用 status=failed、result=null，不伪装成业务 NEEDS_REVIEW。
- 模型可见完整 policy，但不可见 reference_result 或 teaching_policy_id。
- 输入文本和工具数据作为数据处理；prompt 中防注入要求不是安全保证。
- 不提交 checkpoint、凭据、模型权重、虚拟环境或运行日志，不打印整份进程环境。

## Commands from the actual repository root

```bash
uv sync --frozen --all-groups
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
uv run --frozen moderation-demo run --backend scripted --case threat-direct
```

云端默认 uv 缓存只读时，指定工作区内的 UV_CACHE_DIR；不要降低 TLS 或校验要求。
模型配置：MODERATION_BASE_URL、MODERATION_MODEL、可选 MODERATION_API_KEY。

## Learning records

实质变化后更新 learning-progress.md，区分用户确认已学、程序已验证、尚未测试和下一步。
代码通过不等于用户已掌握；不要替用户勾选学习完成。
