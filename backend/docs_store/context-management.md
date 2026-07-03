# 上下文管理说明

## 分层组装

每次请求的 messages 由三层构成：

1. **system**：角色设定 + memory.md 长期记忆全文 + 早前对话摘要（若有）
2. **最近对话窗口**：最近 RECENT_KEEP 轮的原始消息（含工具调用与结果）
3. 工具 schema 独立经 tools 参数传入，不占 messages

Agent 的思考过程（reasoning）只用于前端展示，不回填进后续请求的上下文。

## 总结压缩

当距上次压缩满 MAX_TURNS（默认 10）轮，或手动调用 compress 接口时，
系统用 LLM 把较早的消息压缩成一段摘要，原始消息归档，
之后的 context 只包含摘要 + 最近几轮原文。
