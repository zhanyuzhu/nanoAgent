from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import app.tools  # noqa: F401 - 触发工具注册
from app.agent.events import ErrorEvent
from app.agent.loop import AgentLoop
from app.context.summarizer import compress
from app.schemas import (
    ChatRequest,
    CompressResponse,
    MemoryResponse,
    SessionCreateResponse,
    SessionDetail,
    SessionSummary,
)
from app.sessions.db import close_db, get_db
from app.sessions.models import Session
from app.sessions.store import store
from app.tools.memory import load_memory


@asynccontextmanager
async def lifespan(_: FastAPI):
    await get_db()
    yield
    await close_db()


app = FastAPI(title="nanoAgent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _get_session_or_404(session_id: str) -> Session:
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return session


@app.post("/api/sessions", response_model=SessionCreateResponse)
async def create_session():
    session = await store.create()
    return SessionCreateResponse(session_id=session.id)


@app.get("/api/sessions", response_model=list[SessionSummary])
async def list_sessions():
    rows = await store.list_sessions()
    return [SessionSummary(session_id=r.pop("id"), **r) for r in rows]


@app.get("/api/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str):
    session = await _get_session_or_404(session_id)
    return SessionDetail(
        session_id=session.id,
        turn_count=session.turn_count,
        turns_since_compress=session.turns_since_compress,
        created_at=session.created_at,
        updated_at=session.updated_at,
        summary=session.summary,
        messages=[{"seq": m.seq, "archived": m.archived, **m.data} for m in session.messages],
    )


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    if not await store.delete(session_id):
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    return {"deleted": session_id}


@app.post("/api/sessions/{session_id}/chat")
async def chat(session_id: str, request: ChatRequest):
    session = await _get_session_or_404(session_id)
    lock = store.lock(session_id)
    if lock.locked():
        raise HTTPException(status_code=409, detail="session is busy with another request")

    async def event_stream():
        async with lock:
            try:
                agent = AgentLoop(session, store)
                async for event in agent.run_turn(request.message, request.images):
                    yield event.to_sse()
            except Exception as e:  # noqa: BLE001 - 流已开始，错误只能经 SSE 下发
                yield ErrorEvent(message=f"{type(e).__name__}: {e}").to_sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/sessions/{session_id}/compress", response_model=CompressResponse)
async def compress_session(session_id: str):
    session = await _get_session_or_404(session_id)
    async with store.lock(session_id):
        compressed, detail = await compress(session, store)
    if compressed:
        return CompressResponse(compressed=True, summary=detail)
    return CompressResponse(compressed=False, reason=detail)


@app.get("/api/memory", response_model=MemoryResponse)
async def get_memory():
    return MemoryResponse(content=load_memory())
