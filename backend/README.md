# nanoAgent Backend

从零实现的最小可用 Agent Runtime：自实现 agent loop / 工具调度 / 会话与上下文管理，
不依赖任何现成 Agent 框架。FastAPI + SSE 交付，LLM 为 DashScope OpenAI 兼容接口的
`qwen3-vl-plus`（原生 reasoning + function calling + 图像输入）。

## 启动

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
# .env 中配置 ALIBABA_API_KEY 等（见 app/config.py）
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

运行测试：`.venv\Scripts\python -m pytest`

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/sessions` | 新建会话窗口 |
| GET | `/api/sessions` | 列出所有会话 |
| GET | `/api/sessions/{id}` | 会话详情 + 完整消息历史（含 archived 标记） |
| DELETE | `/api/sessions/{id}` | 删除会话 |
| POST | `/api/sessions/{id}/chat` | SSE 流式对话，body: `{"message": str, "images": [url]?}` |
| POST | `/api/sessions/{id}/compress` | 手动触发历史总结压缩 |
| GET | `/api/memory` | 查看长期记忆内容 |

## SSE 事件协议

每个内容块（`reasoning` / `text` / `tool`）都有完整生命周期，便于前端按块渲染：

```
event: block_start   data: {"block_id":"1-1","block_type":"reasoning"}
event: block_delta   data: {"block_id":"1-1","delta":"..."}
event: block_end     data: {"block_id":"1-1"}
```

- tool 块：`block_start` 带 `tool_name`，`block_delta` 为工具参数（arguments）增量，
  `block_end` 带最终 `arguments` / `result` / `status`（ok|error）；
- 请求以 `done`（`{"turn_count", "compressed"}`）或 `error` 事件收尾。

## 架构

```
app/
├── main.py               # FastAPI 路由 + SSE handler
├── config.py             # 配置（max_iterations/max_turns/recent_keep 等）
├── llm.py                # DashScope OpenAI 兼容封装（stream + enable_thinking）
├── agent/
│   ├── loop.py           # 核心 agent loop + 流式 delta 三路解析
│   └── events.py         # 块级 SSE 事件协议
├── tools/
│   ├── registry.py       # @tool 装饰器注册 + pydantic 自动生成 JSON Schema + dispatch
│   ├── calculator.py     # AST 白名单安全求值
│   ├── search.py         # mock 搜索
│   ├── read_docs.py      # 读取 docs_store/ 文档
│   └── memory.py         # save_memory：长期记忆写入 data/memory.md
├── sessions/             # 内存热缓存 + SQLite write-through，重启可重建
└── context/
    ├── assembler.py      # context 分层组装：system(角色+记忆+摘要) + 最近 K 轮
    └── summarizer.py     # LLM 总结压缩，原始消息归档
```

### 核心循环

1. 用户消息入会话 → 组装 context → 带工具 schema 流式请求 LLM；
2. 逐 delta 解析 `reasoning_content` / `content` / `tool_calls` 三路，实时下发块事件；
3. 有工具调用则校验参数、执行、以 `role=tool` 回填后继续循环（上限 `max_iterations=8`，
   最后一轮以 `tool_choice="none"` 强制直答）；无工具调用则本轮结束；
4. 距上次压缩满 `max_turns=10` 轮时自动触发总结压缩（也可经接口手动触发）：
   较早消息由 LLM 压成摘要并归档，context 只保留摘要 + 最近几轮原文。

### 上下文取舍

- 思考过程（reasoning）只作 SSE 展示与历史留存，不回填后续请求；
- 工具 schema 独立走 `tools` 参数，不占 messages；
- 长期记忆 `data/memory.md` 由模型经 `save_memory` 工具写入，每次组装 system prompt
  时全文注入，天然跨会话生效。
