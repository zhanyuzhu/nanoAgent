import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { createSession, deleteSession, listSessions } from "./api";
import { chatStore } from "./chatStore";
import ChatView from "./components/ChatView";
import Sidebar from "./components/Sidebar";
import type { SessionInfo } from "./types";

export default function App() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  // 无会话状态下输入的首条消息：先建会话，再由新挂载的 ChatView 发送
  const [pendingFirst, setPendingFirst] = useState<string | null>(null);

  const streamingIds = useSyncExternalStore(
    chatStore.subscribeGlobal,
    chatStore.getStreamingIds
  );

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await listSessions());
    } catch (e) {
      console.error("加载会话列表失败", e);
    }
  }, []);

  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  useEffect(() => {
    chatStore.setTurnListener(() => void refreshSessions());
    return () => chatStore.setTurnListener(null);
  }, [refreshSessions]);

  const handleNew = useCallback(async () => {
    const id = await createSession();
    setCurrentId(id);
    await refreshSessions();
  }, [refreshSessions]);

  const handleFirstSend = useCallback(
    async (text: string) => {
      const id = await createSession();
      setPendingFirst(text);
      setCurrentId(id);
      await refreshSessions();
    },
    [refreshSessions]
  );

  const handleDelete = useCallback(
    async (id: string) => {
      await deleteSession(id);
      chatStore.remove(id);
      setCurrentId((cur) => (cur === id ? null : cur));
      await refreshSessions();
    },
    [refreshSessions]
  );

  return (
    <div className="app">
      <Sidebar
        sessions={sessions}
        currentId={currentId}
        streamingIds={streamingIds}
        onSelect={setCurrentId}
        onNew={() => void handleNew()}
        onDelete={(id) => void handleDelete(id)}
      />
      <ChatView
        key={currentId ?? "empty"}
        sessionId={currentId}
        initialMessage={pendingFirst}
        onInitialConsumed={() => setPendingFirst(null)}
        onSendWithoutSession={(text) => void handleFirstSend(text)}
      />
    </div>
  );
}
