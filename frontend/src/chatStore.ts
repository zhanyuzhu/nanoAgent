/**
 * 会话级聊天状态 store（模块单例，独立于组件生命周期）。
 *
 * SSE 消费循环挂在 store 上：切换会话只是换了订阅者，流继续写入
 * 对应 session 的状态；切回时看到的就是实时进行中的内容。
 * 组件经 useSyncExternalStore 订阅（见 useChat.ts）。
 */

import { getSession, streamChat } from "./api";
import type { Block, ChatItem, SSEEvent, StoredMessage } from "./types";

export interface ChatState {
  items: ChatItem[];
  streaming: boolean;
  historyLoaded: boolean;
}

export const EMPTY_STATE: ChatState = { items: [], streaming: false, historyLoaded: false };

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
      return { ...state, items, streaming: false };
    }
    case "error":
      return {
        ...state,
        streaming: false,
        items: [
          ...state.items,
          { kind: "error", id: nextId(), message: event.data.message },
        ],
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

class ChatStore {
  private states = new Map<string, ChatState>();
  private sessionListeners = new Map<string, Set<() => void>>();
  private globalListeners = new Set<() => void>();
  private aborts = new Map<string, AbortController>();
  private streamingIdsCache: string[] = [];
  private turnListener: (() => void) | null = null;

  setTurnListener(cb: (() => void) | null): void {
    this.turnListener = cb;
  }

  getState = (sessionId: string): ChatState => {
    return this.states.get(sessionId) ?? EMPTY_STATE;
  };

  subscribe = (sessionId: string, cb: () => void): (() => void) => {
    let set = this.sessionListeners.get(sessionId);
    if (!set) {
      set = new Set();
      this.sessionListeners.set(sessionId, set);
    }
    set.add(cb);
    return () => set.delete(cb);
  };

  subscribeGlobal = (cb: () => void): (() => void) => {
    this.globalListeners.add(cb);
    return () => this.globalListeners.delete(cb);
  };

  /** 流式进行中的会话 id（快照缓存引用，供 useSyncExternalStore） */
  getStreamingIds = (): string[] => this.streamingIdsCache;

  private setState(sessionId: string, next: ChatState): void {
    this.states.set(sessionId, next);
    const ids = [...this.states].filter(([, s]) => s.streaming).map(([id]) => id);
    if (
      ids.length !== this.streamingIdsCache.length ||
      ids.some((id, i) => id !== this.streamingIdsCache[i])
    ) {
      this.streamingIdsCache = ids;
    }
    this.sessionListeners.get(sessionId)?.forEach((cb) => cb());
    this.globalListeners.forEach((cb) => cb());
  }

  private update(sessionId: string, fn: (s: ChatState) => ChatState): void {
    this.setState(sessionId, fn(this.getState(sessionId)));
  }

  async loadHistory(sessionId: string): Promise<void> {
    const current = this.getState(sessionId);
    // 已有活流或已加载过：store 里的状态比落库历史更新，不覆盖
    if (current.streaming || current.historyLoaded) return;
    try {
      const detail = await getSession(sessionId);
      const latest = this.getState(sessionId);
      if (latest.streaming || latest.historyLoaded) return; // 拉取期间开始了新流
      this.setState(sessionId, {
        items: historyToItems(detail.messages),
        streaming: false,
        historyLoaded: true,
      });
    } catch (e) {
      this.update(sessionId, (s) => ({
        ...s,
        historyLoaded: true,
        items: [...s.items, { kind: "error", id: nextId(), message: String(e) }],
      }));
    }
  }

  async send(sessionId: string, message: string): Promise<void> {
    if (this.getState(sessionId).streaming) return;
    const controller = new AbortController();
    this.aborts.set(sessionId, controller);
    this.update(sessionId, (s) => ({
      ...s,
      streaming: true,
      items: [...s.items, { kind: "user", id: nextId(), content: message }],
    }));
    try {
      await streamChat(
        sessionId,
        message,
        (event) => this.update(sessionId, (s) => applySSE(s, event)),
        controller.signal
      );
      this.update(sessionId, (s) => ({ ...s, streaming: false }));
    } catch (e) {
      if (controller.signal.aborted) {
        this.update(sessionId, (s) => ({
          ...s,
          streaming: false,
          items: [...s.items, { kind: "notice", id: nextId(), text: "已停止生成" }],
        }));
      } else {
        this.update(sessionId, (s) => ({
          ...s,
          streaming: false,
          items: [...s.items, { kind: "error", id: nextId(), message: String(e) }],
        }));
      }
    } finally {
      this.aborts.delete(sessionId);
      this.turnListener?.();
    }
  }

  stop(sessionId: string): void {
    this.aborts.get(sessionId)?.abort();
  }

  toggleBlock(sessionId: string, blockId: string): void {
    this.update(sessionId, (s) => ({
      ...s,
      items: patchBlock(s.items, blockId, (b) => ({ ...b, open: !b.open })),
    }));
  }

  addNotice(sessionId: string, text: string): void {
    this.update(sessionId, (s) => ({
      ...s,
      items: [...s.items, { kind: "notice", id: nextId(), text }],
    }));
  }

  remove(sessionId: string): void {
    this.aborts.get(sessionId)?.abort();
    this.aborts.delete(sessionId);
    this.states.delete(sessionId);
    this.sessionListeners.delete(sessionId);
    this.streamingIdsCache = this.streamingIdsCache.filter((id) => id !== sessionId);
    this.globalListeners.forEach((cb) => cb());
  }
}

export const chatStore = new ChatStore();
