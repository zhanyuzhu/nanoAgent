from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    # 图片 URL 或 data:image/...;base64,... 形式的 data URL
    images: list[str] = Field(default_factory=list)


class SessionCreateResponse(BaseModel):
    session_id: str


class SessionSummary(BaseModel):
    session_id: str
    title: str = "新对话"
    turn_count: int
    turns_since_compress: int
    created_at: str
    updated_at: str


class SessionDetail(SessionSummary):
    summary: str
    messages: list[dict[str, Any]]


class CompressResponse(BaseModel):
    compressed: bool
    reason: str = ""
    summary: str = ""


class MemoryResponse(BaseModel):
    content: str
