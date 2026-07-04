# nanoAgent

自建 Agent Runtime（基本循环 + 工具调度 + 会话与上下文管理），
不依赖 langgraph 等现成 Agent 框架。后端 Python + FastAPI + SSE，前端 React，
LLM 为 DashScope OpenAI 兼容接口的 `qwen3-vl-plus`。

## 运行方式

**后端**（先启动，端口 8000）：

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
# backend/.env 中配置 ALIBABA_API_KEY（模型与 base_url 已有默认值）
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

**前端**（端口 5173，`/api` 自动代理到后端）：

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 即可对话。测试：`cd backend && .venv\Scripts\python -m pytest`。

## 系统设计

### 核心循环：ReAct模式
1. 接收用户输入，追加进 session 消息历史
2. 组装 context（system + 长期记忆 + 摘要 + 最近对话窗口），带工具 schema 请求 LLM
3. LLM 决定直接回答或调用工具
4. 有工具调用则执行并把结果回填，继续循环；否则把最终答案流式返回用户
5. 单次请求内工具循环上限 `max_iterations=8`，达到后强制直答

全程以块级 SSE 事件下发（`block_start / block_delta / block_end` + `done / error`），
reasoning、tool call、text 三类块均有完整的开始/结束信号，前端据此流式渲染。

### 工具机制

工具通过装饰器注册到中央 Registry，每个工具包含名称、描述和由 pydantic 模型自动生成的
参数 JSON Schema，LLM 基于 schema 自主决策调用。内置四个工具：calculator、search（mock）、read_docs（读取 `backend/docs_store/`）、save_memory（长期记忆）。

### 会话管理

每个聊天窗口对应独立 `session_id`，消息历史、轮次计数和摘要相互隔离。存储为内存热缓存 +
SQLite write-through，重启后按 session_id 自动重建，可随时切回任意窗口继续。

### 上下文管理

每次请求的 messages 分三层：

1. **system**：角色设定 + memory.md 长期记忆全文 + 早前对话摘要（若有）
2. **最近对话窗口**：最近 `RECENT_KEEP=4` 轮原始消息（含工具调用与结果）
3. 工具 schema 独立经 `tools` 参数传入

Agent 的思考过程（reasoning）只用于前端展示与历史留存，不回填后续请求的上下文。

**总结压缩**：距上次压缩满 `MAX_TURNS=10` 轮，或手动调用 compress 接口时，用 LLM 把较早的
消息压缩成一段摘要并归档原始消息，之后的 context 只含摘要 + 最近几轮原文。

## Memory（长期记忆）

跨会话记忆基于单个文件 `backend/data/memory.md`：

- **写入时机**：`save_memory` 是注册给 LLM 的第 4 个工具，system prompt 指示模型在用户
  表达跨会话偏好（如"以后数值保留两位小数"）、关于自己的长期事实（如姓名）、或纠正
  agent 做法时调用。每条记忆是一行带日期的 bullet，追加写入并做重复检测；临时性的
  对话细节不会被记录。
- **召回时机**：不做检索——**每次请求**组装 messages 时无条件读入 memory.md 全文。
  因此记忆写入后立即生效，且天然对所有 session 生效（新窗口第一句话就"记得你"）。
- **放置方式**：注入 system prompt 的第二段，位于角色设定之后、对话摘要之前，
  以「## 长期记忆（跨会话，来自 memory 文件）」为标题成段呈现（见
  `backend/app/context/assembler.py::build_system_prompt`）。放在 system 层而非对话流中，
  使其优先级高于普通对话内容，也不受滑动窗口截断和总结压缩影响。

可通过 `GET /api/memory` 查看当前记忆内容。

