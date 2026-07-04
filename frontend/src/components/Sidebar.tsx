import type { SessionInfo } from "../types";

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

interface Props {
  sessions: SessionInfo[];
  currentId: string | null;
  streamingIds: string[];
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export default function Sidebar({
  sessions,
  currentId,
  streamingIds,
  onSelect,
  onNew,
  onDelete,
}: Props) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-mark">〇</span> nanoAgent
      </div>
      <button className="new-chat-btn" onClick={onNew}>
        ＋ 新对话
      </button>
      <div className="session-list">
        {sessions.map((s) => (
          <div
            key={s.session_id}
            className={`session-item ${s.session_id === currentId ? "active" : ""}`}
            onClick={() => onSelect(s.session_id)}
          >
            <div className="session-title">
              {streamingIds.includes(s.session_id) && (
                <span className="streaming-dot" title="正在生成" />
              )}
              {s.title}
            </div>
            <div className="session-meta">
              {relativeTime(s.updated_at)} · {s.turn_count} 轮
            </div>
            <button
              className="session-delete"
              title="删除会话"
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`删除会话「${s.title}」？`)) onDelete(s.session_id);
              }}
            >
              ✕
            </button>
          </div>
        ))}
        {sessions.length === 0 && <div className="session-empty">暂无会话</div>}
      </div>
    </aside>
  );
}
