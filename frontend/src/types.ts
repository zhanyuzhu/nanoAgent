export interface SessionInfo {
  session_id: string;
  title: string;
  turn_count: number;
  turns_since_compress: number;
  created_at: string;
  updated_at: string;
}

export interface SessionDetail extends SessionInfo {
  summary: string;
  messages: StoredMessage[];
}

/** 后端落库的 OpenAI 格式消息（assistant 可带 reasoning / tool_calls） */
export interface StoredMessage {
  seq: number;
  archived: boolean;
  role: "user" | "assistant" | "tool";
  content: string | { type: string; text?: string; image_url?: { url: string } }[];
  reasoning?: string;
  tool_calls?: {
    id: string;
    function: { name: string; arguments: string };
  }[];
  tool_call_id?: string;
}

export type BlockType = "reasoning" | "text" | "tool";

export interface Block {
  id: string;
  type: BlockType;
  /** reasoning/text 的正文；tool 块流式期间为 arguments 原始增量 */
  text: string;
  toolName?: string;
  args?: unknown;
  result?: string;
  status?: "ok" | "error";
  open: boolean;
  done: boolean;
}

export type ChatItem =
  | { kind: "user"; id: string; content: string }
  | { kind: "block"; block: Block }
  | { kind: "error"; id: string; message: string }
  | { kind: "notice"; id: string; text: string };

export type SSEEvent =
  | {
      event: "block_start";
      data: { block_id: string; block_type: BlockType; tool_name?: string };
    }
  | { event: "block_delta"; data: { block_id: string; delta: string } }
  | {
      event: "block_end";
      data: {
        block_id: string;
        tool_name?: string;
        arguments?: unknown;
        result?: string;
        status?: "ok" | "error";
      };
    }
  | { event: "done"; data: { turn_count: number; compressed: boolean } }
  | { event: "error"; data: { message: string } };
