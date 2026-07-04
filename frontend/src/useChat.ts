import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { getSession, streamChat } from "./api";
import type { Block, ChatItem, SSEEvent, StoredMessage } from "./types";

interface ChatState {
  items: ChatItem[];
  streaming: boolean;
}

type Action =
  | { type: "reset"; items: ChatItem[] }
  | { type: "user"; content: string }
  | { type: "sse"; event: SSEEvent }
  | { type: "toggle"; blockId: string }
  | { type: "stream_end" }
  | { type: "error"; message: string }
  | { type: "notice"; text: string };

let uid = 0;
const nextId = () => `local-${++uid}`;

function patchBlock(
  items: ChatItem[],
  blockId: string,
  patch: (b: Block) => Block
): ChatItem[] {
  return items.map((item) =>
    item.kind === "block" && item.block.id === blockId
      ? { ...item, block: patch(item.block) }
      : item
  );
}

function applySSE(state: ChatState, event: SSEEvent): ChatState {
  switch (event.event) {
    case "block_start": {
      const { block_id, block_type, tool_name } = event.data;
      const block: Block = {
        id: block_id,
        type: block_type,
        text: "",
        toolName: tool_name ?? undefined,
        // reasoning 流式期间展开，结束自动折叠；tool 默认折叠
        open: block_type !== "tool",
        done: false,
      };
      return { ...state, items: [...state.items, { kind: "block", block }] };
    }
    case "block_delta":
      return {
        ...state,
        items: patchBlock(state.items, event.data.block_id, (b) => ({
          ...b,
          text: b.text + event.data.delta,
        })),
      };
    case "block_end": {
      const { block_id, tool_name, arguments: args, result, status } = event.data;
      return {
        ...state,
        items: patchBlock(state.items, block_id, (b) => ({
          ...b,
          done: true,
          open: b.type === "text" ? b.open : false,
          toolName: tool_name ?? b.toolName,
          args: args ?? b.args,
          result: result ?? b.result,
          status: status ?? b.status,
        })),
      };
    }
    case "done": {
      const items = event.data.compressed
        ? [
            ...state.items,
            { kind: "notice" as const, id: nextId(), text: "较早的对话已压缩为摘要" },
          ]
        : state.items;
      return { items, streaming: false };
    }
    case "error":
      return {
        streaming: false,
        items: [
          ...state.items,
          { kind: "error", id: nextId(), message: event.data.message },
        ],
      };
  }
}

function reducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "reset":
      return { items: action.items, streaming: false };
    case "user":
      return {
        streaming: true,
        items: [...state.items, { kind: "user", id: nextId(), content: action.content }],
      };
    case "sse":
      return applySSE(state, action.event);
    case "toggle":
      return {
        ...state,
        items: patchBlock(state.items, action.blockId, (b) => ({ ...b, open: !b.open })),
      };
    case "stream_end":
      return { ...state, streaming: false };
    case "error":
      return {
        streaming: false,
        items: [...state.items, { kind: "error", id: nextId(), message: action.message }],
      };
    case "notice":
      return {
        ...state,
        items: [...state.items, { kind: "notice", id: nextId(), text: action.text }],
      };
  }
}

function contentToText(content: StoredMessage["content"]): string {
  if (typeof content === "string") return content;
  return content
    .map((p) => (p.type === "text" ? p.text ?? "" : "[图片]"))
    .join(" ")
    .trim();
}

/** 把落库的消息历史重建为与流式一致的 ChatItem 结构。 */
export function historyToItems(messages: StoredMessage[]): ChatItem[] {
  const toolResults = new Map<string, string>();
  for (const m of messages) {
    if (m.role === "tool" && m.tool_call_id) {
      toolResults.set(m.tool_call_id, typeof m.content === "string" ? m.content : "");
    }
  }

  const items: ChatItem[] = [];
  for (const m of messages) {
    if (m.role === "user") {
      items.push({ kind: "user", id: `h-${m.seq}`, content: contentToText(m.content) });
    } else if (m.role === "assistant") {
      if (m.reasoning) {
        items.push({
          kind: "block",
          block: {
            id: `h-${m.seq}-r`,
            type: "reasoning",
            text: m.reasoning,
            open: false,
            done: true,
          },
        });
      }
      for (const tc of m.tool_calls ?? []) {
        let args: unknown;
        try {
          args = JSON.parse(tc.function.arguments || "{}");
        } catch {
          args = { _raw: tc.function.arguments };
        }
        const result = toolResults.get(tc.id);
        items.push({
          kind: "block",
          block: {
            id: `h-${m.seq}-${tc.id}`,
            type: "tool",
            text: tc.function.arguments,
            toolName: tc.function.name,
            args,
            result,
            status: result?.startsWith("Error") ? "error" : "ok",
            open: false,
            done: true,
          },
        });
      }
      const text = contentToText(m.content);
      if (text) {
        items.push({
          kind: "block",
          block: { id: `h-${m.seq}-t`, type: "text", text, open: true, done: true },
        });
      }
    }
  }
  return items;
}

export function useChat(sessionId: string | null, onTurnFinished: () => void) {
  const [state, dispatch] = useReducer(reducer, { items: [], streaming: false });
  const [loading, setLoading] = useState(false);
  // 历史加载完成前不允许发送：reset(items) 会清掉先入队的 user 项
  const [historyReady, setHistoryReady] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // 注意：不在此处 abort 在途请求 —— ChatView 按 session 整体重挂载，
  // 让后台流跑完可以保证该轮消息在服务端完整落库；中断只经显式 stop()。
  useEffect(() => {
    dispatch({ type: "reset", items: [] });
    if (!sessionId) return;
    let cancelled = false;
    setLoading(true);
    setHistoryReady(false);
    getSession(sessionId)
      .then((detail) => {
        if (!cancelled) dispatch({ type: "reset", items: historyToItems(detail.messages) });
      })
      .catch((e) => {
        if (!cancelled) dispatch({ type: "error", message: String(e) });
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setHistoryReady(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const send = useCallback(
    async (message: string) => {
      if (!sessionId) return;
      const controller = new AbortController();
      abortRef.current = controller;
      dispatch({ type: "user", content: message });
      try {
        await streamChat(
          sessionId,
          message,
          (event) => dispatch({ type: "sse", event }),
          controller.signal
        );
        dispatch({ type: "stream_end" });
      } catch (e) {
        if (controller.signal.aborted) {
          dispatch({ type: "stream_end" });
          dispatch({ type: "notice", text: "已停止生成" });
        } else {
          dispatch({ type: "error", message: String(e) });
        }
      } finally {
        onTurnFinished();
      }
    },
    [sessionId, onTurnFinished]
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);
  const toggleBlock = useCallback(
    (blockId: string) => dispatch({ type: "toggle", blockId }),
    []
  );
  const addNotice = useCallback(
    (text: string) => dispatch({ type: "notice", text }),
    []
  );

  return { ...state, loading, historyReady, send, stop, toggleBlock, addNotice };
}
