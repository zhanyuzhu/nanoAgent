# nanoAgent Frontend

React + Vite + TypeScript 实现的类 Claude 聊天界面，配合 `../backend` 使用。

## 启动

```bash
npm install
npm run dev        # http://localhost:5173，/api 代理到后端 :8000（先启动后端）
npm run build      # 类型检查 + 产物构建
```

## 功能

- **块级流式渲染**：对接后端 SSE 协议（`block_start` / `block_delta` / `block_end`），
  reasoning（思考中流式展开、结束自动折叠）、tool（可折叠卡片：参数 JSON + 结果 + 状态）、
  text（markdown 渲染，流式光标）三类块。
- **多会话 + 流式不中断切换**：聊天状态与 SSE 消费循环放在组件外的会话级 store
  （`src/chatStore.ts`，`Map<sessionId, ChatState>`），组件经 `useSyncExternalStore` 订阅。
  流式进行中可自由切换会话：流在后台继续写 store，切回即见实时进度；侧栏对
  流式中的会话显示脉冲指示点。不同会话可并行生成。
- 侧栏新建/切换/删除，标题取首条消息；首次进入会话时从落库历史重建块结构
  （`src/chatStore.ts::historyToItems`），之后状态常驻内存（含块折叠状态）。
- **停止生成**（AbortController 中断 SSE fetch）、**压缩历史**按钮、压缩发生时的提示条。

## 结构

- `src/api.ts` — REST 封装 + fetch ReadableStream 手写 SSE 解析
- `src/chatStore.ts` — 会话级外部状态 store：SSE 事件 reducer、流生命周期、历史重建
- `src/useChat.ts` — 薄 hook：useSyncExternalStore 订阅 + 首次历史加载
- `src/components/` — Sidebar / ChatView / Composer / ReasoningBlock / ToolBlock / TextBlock
- `src/styles.css` — 手写 Claude 风格样式（无 UI 框架）

注意：入口未包 React StrictMode——dev 下 effect 双跑会中止进行中的 SSE 流。
