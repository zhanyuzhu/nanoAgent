from dataclasses import dataclass, field
from typing import Any


@dataclass
class MessageRecord:
    seq: int
    data: dict[str, Any]  # OpenAI 格式消息，assistant 消息可额外含 "reasoning" 供展示
    archived: bool = False


@dataclass
class Session:
    id: str
    summary: str = ""
    turn_count: int = 0
    turns_since_compress: int = 0
    created_at: str = ""
    updated_at: str = ""
    messages: list[MessageRecord] = field(default_factory=list)

    @property
    def active_messages(self) -> list[MessageRecord]:
        return [m for m in self.messages if not m.archived]

    def next_seq(self) -> int:
        return self.messages[-1].seq + 1 if self.messages else 0
