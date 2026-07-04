import { useCallback, useEffect, useSyncExternalStore } from "react";

import { chatStore, EMPTY_STATE, type ChatState } from "./chatStore";

/** 订阅指定会话的聊天状态切片；状态本体与流的生命周期都在 chatStore。 */
export function useChat(sessionId: string | null): ChatState {
  const subscribe = useCallback(
    (cb: () => void) => (sessionId ? chatStore.subscribe(sessionId, cb) : () => {}),
    [sessionId]
  );
  const getSnapshot = useCallback(
    () => (sessionId ? chatStore.getState(sessionId) : EMPTY_STATE),
    [sessionId]
  );
  const state = useSyncExternalStore(subscribe, getSnapshot);

  useEffect(() => {
    if (sessionId) void chatStore.loadHistory(sessionId);
  }, [sessionId]);

  return state;
}
