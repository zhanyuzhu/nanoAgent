"""save_memory 工具：把跨会话有用的事实合并进 data/memory.md。

memory.md 全文会在每次组装 system prompt 时注入，因此天然跨 session 生效。
"""

from datetime import date

from pydantic import BaseModel, Field

from app.config import settings
from app.tools.registry import tool


def load_memory() -> str:
    if settings.memory_path.is_file():
        return settings.memory_path.read_text(encoding="utf-8").strip()
    return ""


class SaveMemoryParams(BaseModel):
    fact: str = Field(
        description="One concise, self-contained fact/preference/correction worth "
        "remembering across sessions, e.g. 'User prefers answers in Chinese.'"
    )


@tool(
    name="save_memory",
    description="Persist a long-term memory that should survive across sessions. "
    "Call this when the user states a lasting preference, a fact about themselves, "
    "or corrects how you should behave. Do NOT use it for transient conversation details.",
    params=SaveMemoryParams,
)
async def save_memory(params: SaveMemoryParams) -> str:
    fact = " ".join(params.fact.split())
    existing = load_memory()
    if fact in existing:
        return "Already remembered."
    line = f"- [{date.today().isoformat()}] {fact}"
    content = f"{existing}\n{line}".strip() + "\n"
    settings.memory_path.write_text(content, encoding="utf-8")
    return f"Remembered: {fact}"
