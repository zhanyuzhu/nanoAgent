# nanoAgent 设计文档

nanoAgent 是一个从零实现的最小可用 Agent Runtime，不依赖任何现成 Agent 框架。

## 核心循环

1. 接收用户输入，追加进 session 消息历史
2. 组装 context（system + 长期记忆 + 摘要 + 最近对话窗口），带工具 schema 请求 LLM
3. LLM 决定直接回答或调用工具
4. 有工具调用则执行并把结果回填，继续循环；否则把最终答案返回用户
5. 单次请求内工具循环上限为 max_iterations，达到后强制直答

## 工具机制

工具通过装饰器注册到中央 Registry，每个工具包含名称、描述和由 pydantic
模型自动生成的参数 JSON Schema。LLM 基于 schema 自主决策调用。
