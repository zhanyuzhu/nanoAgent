"""Session 存储：内存 dict 热缓存 + SQLite write-through。

- 所有写操作先改内存对象、同步落 SQLite（write-through）；
- 缓存 miss（如服务重启后）从 SQLite 整体重建 Session，支持随时切回任一窗口继续。
- 每个 session 一把 asyncio.Lock，防同一 session 并发 chat 交叉写。
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.sessions.db import get_db
from app.sessions.models import MessageRecord, Session


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _extract_title(content_json: str | None, limit: int = 40) -> str:
    """从首条 user 消息提取会话标题；多模态消息取文本部分。"""
    if not content_json:
        return "新对话"
    content = json.loads(content_json).get("content", "")
    if isinstance(content, list):
        content = " ".join(p.get("text", "") for p in content if p.get("type") == "text")
    title = " ".join(str(content).split())
    return title[:limit] if title else "新对话"


class SessionStore:
    def __init__(self) -> None:
        self._cache: dict[str, Session] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    async def create(self) -> Session:
        session = Session(id=uuid.uuid4().hex[:12], created_at=_now(), updated_at=_now())
        db = await get_db()
        await db.execute(
            "INSERT INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
            (session.id, session.created_at, session.updated_at),
        )
        await db.commit()
        self._cache[session.id] = session
        return session

    async def get(self, session_id: str) -> Session | None:
        if session_id in self._cache:
            return self._cache[session_id]
        db = await get_db()
        cur = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cur.fetchone()
        if row is None:
            return None
        session = Session(
            id=row["id"],
            summary=row["summary"],
            turn_count=row["turn_count"],
            turns_since_compress=row["turns_since_compress"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        cur = await db.execute(
            "SELECT seq, content_json, archived FROM messages "
            "WHERE session_id = ? ORDER BY seq",
            (session_id,),
        )
        async for m in cur:
            session.messages.append(
                MessageRecord(
                    seq=m["seq"],
                    data=json.loads(m["content_json"]),
                    archived=bool(m["archived"]),
                )
            )
        self._cache[session_id] = session
        return session

    async def list_sessions(self) -> list[dict[str, Any]]:
        db = await get_db()
        cur = await db.execute(
            "SELECT s.id, s.turn_count, s.turns_since_compress, s.created_at, s.updated_at, "
            "(SELECT m.content_json FROM messages m WHERE m.session_id = s.id "
            " AND m.role = 'user' ORDER BY m.seq LIMIT 1) AS first_user "
            "FROM sessions s ORDER BY s.updated_at DESC"
        )
        rows = []
        for r in await cur.fetchall():
            row = dict(r)
            row["title"] = _extract_title(row.pop("first_user"))
            rows.append(row)
        return rows

    async def delete(self, session_id: str) -> bool:
        db = await get_db()
        cur = await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
        self._cache.pop(session_id, None)
        self._locks.pop(session_id, None)
        return cur.rowcount > 0

    async def append_message(self, session: Session, data: dict[str, Any]) -> MessageRecord:
        record = MessageRecord(seq=session.next_seq(), data=data)
        session.messages.append(record)
        session.updated_at = _now()
        db = await get_db()
        await db.execute(
            "INSERT INTO messages (session_id, seq, role, content_json) VALUES (?, ?, ?, ?)",
            (session.id, record.seq, data.get("role", ""), json.dumps(data, ensure_ascii=False)),
        )
        await db.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (session.updated_at, session.id)
        )
        await db.commit()
        return record

    async def update_meta(self, session: Session) -> None:
        """把 summary / 轮次计数落盘。"""
        session.updated_at = _now()
        db = await get_db()
        await db.execute(
            "UPDATE sessions SET summary = ?, turn_count = ?, turns_since_compress = ?, "
            "updated_at = ? WHERE id = ?",
            (
                session.summary,
                session.turn_count,
                session.turns_since_compress,
                session.updated_at,
                session.id,
            ),
        )
        await db.commit()

    async def archive_messages(self, session: Session, up_to_seq: int) -> None:
        """把 seq <= up_to_seq 的消息标记为已归档（context 不再使用，历史仍可展示）。"""
        for m in session.messages:
            if m.seq <= up_to_seq:
                m.archived = True
        db = await get_db()
        await db.execute(
            "UPDATE messages SET archived = 1 WHERE session_id = ? AND seq <= ?",
            (session.id, up_to_seq),
        )
        await db.commit()


store = SessionStore()
