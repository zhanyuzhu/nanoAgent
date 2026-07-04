import { useEffect, useRef } from "react";

import { compressSession } from "../api";
import { useChat } from "../useChat";
import Composer from "./Composer";
import ReasoningBlock from "./ReasoningBlock";
import TextBlock from "./TextBlock";
import ToolBlock from "./ToolBlock";

interface Props {
  sessionId: string | null;
  /** 会话创建前用户输入的首条消息，挂载后自动发送 */
  initialMessage: string | null;
  onInitialConsumed: () => void;
  onSendWithoutSession: (text: string) => void;
  onTurnFinished: () => void;
}

export default function ChatView({
  sessionId,
  initialMessage,
  onInitialConsumed,
  onSendWithoutSession,
  onTurnFinished,
}: Props) {
  const { items, streaming, loading, historyReady, send, stop, toggleBlock, addNotice } =
    useChat(sessionId, onTurnFinished);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const sentInitial = useRef(false);

  useEffect(() => {
    // 等历史加载完成再自动发送，避免 reset 清掉刚入队的 user 消息
    if (sessionId && initialMessage && historyReady && !sentInitial.current) {
      sentInitial.current = true;
      onInitialConsumed();
      void send(initialMessage);
    }
  }, [sessionId, initialMessage, historyReady, onInitialConsumed, send]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [items]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (el) {
      stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    }
  };

  const handleCompress = async () => {
    if (!sessionId) return;
    try {
      const res = await compressSession(sessionId);
      addNotice(res.compressed ? "较早的对话已压缩为摘要" : `未压缩：${res.reason}`);
    } catch (e) {
      addNotice(`压缩失败：${String(e)}`);
    }
  };

  return (
    <main className="chat">
      <header className="chat-header">
        <span className="chat-header-title">
          {sessionId ? `会话 ${sessionId}` : "开始新的对话"}
        </span>
        {sessionId && (
          <button className="ghost-btn" onClick={() => void handleCompress()} disabled={streaming}>
            压缩历史
          </button>
        )}
      </header>

      <div className="chat-scroll" ref={scrollRef} onScroll={handleScroll}>
        <div className="chat-column">
          {!sessionId && (
            <div className="hero">
              <div className="hero-mark">✳</div>
              <h1>有什么可以帮你？</h1>
              <p>试试「帮我算一下 (37*89+15)/4」或「查一下项目文档」</p>
            </div>
          )}
          {loading && <div className="notice">加载历史中…</div>}
          {items.map((item) => {
            switch (item.kind) {
              case "user":
                return (
                  <div key={item.id} className="user-row">
                    <div className="user-bubble">{item.content}</div>
                  </div>
                );
              case "block": {
                const b = item.block;
                if (b.type === "reasoning")
                  return <ReasoningBlock key={b.id} block={b} onToggle={toggleBlock} />;
                if (b.type === "tool")
                  return <ToolBlock key={b.id} block={b} onToggle={toggleBlock} />;
                return <TextBlock key={b.id} block={b} />;
              }
              case "error":
                return (
                  <div key={item.id} className="error-box">
                    ⚠ {item.message}
                  </div>
                );
              case "notice":
                return (
                  <div key={item.id} className="notice">
                    {item.text}
                  </div>
                );
            }
          })}
          {streaming && items.at(-1)?.kind === "user" && (
            <div className="pending-dots">
              <span />
              <span />
              <span />
            </div>
          )}
        </div>
      </div>

      <Composer
        streaming={streaming}
        onSend={(text) => {
          stickToBottom.current = true;
          if (sessionId) {
            void send(text);
          } else {
            onSendWithoutSession(text);
          }
        }}
        onStop={stop}
      />
    </main>
  );
}
