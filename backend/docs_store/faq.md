# 常见问题

**Q: 多个聊天窗口会互相影响吗？**
A: 不会。每个窗口对应独立的 session_id，消息历史、轮次计数和摘要都相互隔离，
可以随时切回任意窗口继续对话。

**Q: 关掉服务后历史会丢吗？**
A: 不会。所有 session 和消息都 write-through 持久化到 SQLite，
重启后按 session_id 自动从数据库重建。

**Q: 长期记忆存在哪里？**
A: data/memory.md。当你告诉 agent 一个跨会话有用的偏好或事实时，
它会调用 save_memory 工具写入该文件，之后所有会话的 system prompt 都会带上。
