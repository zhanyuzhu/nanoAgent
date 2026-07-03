"""SSE 事件协议：discriminated-union 的块级事件，含开始/结束信号。

每个内容块（reasoning / text / tool）都有 block_start → block_delta* → block_end
的生命周期，方便前端按块渲染：

  event: block_start   data: {"block_id":"t1-0","block_type":"reasoning"}
  event: block_delta   data: {"block_id":"t1-0","delta":"..."}
  event: block_end     data: {"block_id":"t1-0"}

tool 块的 block_start 带 tool_name，delta 为 arguments 增量，
block_end 带最终 arguments / result / status。
整个请求以 done 或 error 事件收尾。
"""

from typing import Any, ClassVar, Literal

from pydantic import BaseModel


class Event(BaseModel):
    EVENT: ClassVar[str]

    def to_sse(self) -> str:
        return f"event: {self.EVENT}\ndata: {self.model_dump_json(exclude_none=True)}\n\n"


class BlockStart(Event):
    EVENT = "block_start"
    block_id: str
    block_type: Literal["reasoning", "text", "tool"]
    tool_name: str | None = None


class BlockDelta(Event):
    EVENT = "block_delta"
    block_id: str
    delta: str


class BlockEnd(Event):
    EVENT = "block_end"
    block_id: str
    # 以下仅 tool 块携带
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    result: str | None = None
    status: Literal["ok", "error"] | None = None


class Done(Event):
    EVENT = "done"
    turn_count: int
    compressed: bool = False


class ErrorEvent(Event):
    EVENT = "error"
    message: str
