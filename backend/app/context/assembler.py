"""Context 组装：决定每次请求往 messages 里塞什么。

分层结构（tools schema 独立走 tools 参数，不占 messages）：
1. system：角色设定 + 长期记忆（memory.md 全文）+ 早前对话摘要（若有）
2. 最近 RECENT_KEEP 轮未归档对话（1 轮 = user 到最终 assistant，含中间 tool 消息）

刻意不回填的内容：assistant 的思考过程（reasoning）只作为 SSE 过程展示与
历史留存，不进入后续请求的 context。
"""

from typing import Any

from app.config import settings
from app.sessions.models import MessageRecord, Session
from app.tools.memory import load_memory

BASE_SYSTEM_PROMPT = """\
你是 nanoAgent，一个乐于助人的中文 AI 助手。

工具使用原则：
- 任何算术计算都必须使用 calculator 工具，不要心算。
- 需要外部/时效信息时使用 search 工具；需要项目文档时先用 read_docs 列出再阅读。
- 当用户表达跨会话有效的偏好、关于自己的长期事实，或纠正你的做法时，\
调用 save_memory 把它记下来（一次一条、简洁自包含）；临时性的对话细节不要记。
- 工具返回错误时，修正参数重试或换一种方式，不要把原始错误直接甩给用户。

回答原则：先给结论，再给必要的过程；保持简洁。"""

# 保留进 context 的消息字段；"reasoning" 等展示用字段在此被剥离
_KEEP_KEYS = ("role", "content", "tool_calls", "tool_call_id")


def strip_for_context(data: dict[str, Any]) -> dict[str, Any]:
    return {k: data[k] for k in _KEEP_KEYS if k in data}


def take_recent_turns(records: list[MessageRecord], k: int) -> list[MessageRecord]:
    """从尾部取最近 k 轮：窗口总是从某条 user 消息开始，保证 tool 链完整。"""
    if k <= 0:
        return []
    start = 0
    seen_users = 0
    for i in range(len(records) - 1, -1, -1):
        if records[i].data.get("role") == "user":
            seen_users += 1
            if seen_users >= k:
                start = i
                break
    return records[start:]


def build_system_prompt(summary: str) -> str:
    parts = [BASE_SYSTEM_PROMPT]
    memory = load_memory()
    if memory:
        parts.append(f"## 长期记忆（跨会话，来自 memory 文件）\n{memory}")
    if summary:
        parts.append(f"## 早前对话摘要\n以下是本会话较早内容的摘要，原始消息已省略：\n{summary}")
    return "\n\n".join(parts)


def assemble(session: Session) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt(session.summary)}
    ]
    recent = take_recent_turns(session.active_messages, settings.recent_keep)
    messages.extend(strip_for_context(m.data) for m in recent)
    return messages
