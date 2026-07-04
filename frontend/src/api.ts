import type { SessionDetail, SessionInfo, SSEEvent } from "./types";

const BASE = "/api";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export async function createSession(): Promise<string> {
  const data = await json<{ session_id: string }>(
    await fetch(`${BASE}/sessions`, { method: "POST" })
  );
  return data.session_id;
}

export function listSessions(): Promise<SessionInfo[]> {
  return fetch(`${BASE}/sessions`).then((r) => json<SessionInfo[]>(r));
}

export function getSession(id: string): Promise<SessionDetail> {
  return fetch(`${BASE}/sessions/${id}`).then((r) => json<SessionDetail>(r));
}

export async function deleteSession(id: string): Promise<void> {
  await json(await fetch(`${BASE}/sessions/${id}`, { method: "DELETE" }));
}

export function compressSession(
  id: string
): Promise<{ compressed: boolean; reason: string; summary: string }> {
  return fetch(`${BASE}/sessions/${id}/compress`, { method: "POST" }).then((r) =>
    json(r)
  );
}

/** POST + ReadableStream 消费 SSE（EventSource 不支持 POST）。 */
export async function streamChat(
  sessionId: string,
  message: string,
  onEvent: (event: SSEEvent) => void,
  signal: AbortSignal
): Promise<void> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!res.ok || !res.body) {
    const body = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${body.slice(0, 200)}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "";
      let data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (event && data) {
        onEvent({ event, data: JSON.parse(data) } as SSEEvent);
      }
    }
  }
}
