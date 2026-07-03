"""总结压缩：把较早的对话用 LLM 压成摘要，原始消息归档。

触发：距上次压缩满 MAX_TURNS 轮（自动）或调用 compress 接口（手动）。
压缩后 context = 摘要（进 system）+ 最近 COMPRESS_KEEP_RECENT 轮原文。
"""

import json

from app.config import settings
from app.llm import llm
from app.sessions.models import MessageRecord, Session
from app.sessions.store import SessionStore

_SUMMARIZE_PROMPT = """\
你是对话压缩器。把下面的对话历史压缩成一段中文摘要，供 AI 助手作为上下文继续对话使用。
要求：
- 保留：用户的关键信息与偏好、已完成的任务及其结果（含工具算出的具体数值）、未决事项;
- 丢弃：寒暄、重复内容、工具调用的过程细节;
- 若提供了「既有摘要」，把新内容合并进去输出一份完整摘要;
- 直接输出摘要正文，不要任何前缀说明，长度不超过 300 字。"""


def _render(records: list[MessageRecord]) -> str:
    lines: list[str] = []
    for r in records:
        data = r.data
        role = data.get("role")
        content = data.get("content") or ""
        if isinstance(content, list):  # 多模态消息只取文本部分
            content = " ".join(p.get("text", "[图片]") for p in content)
        if role == "assistant" and data.get("tool_calls"):
            calls = ", ".join(
                f"{tc['function']['name']}({tc['function']['arguments']})"
                for tc in data["tool_calls"]
            )
            lines.append(f"assistant: [调用工具 {calls}] {content}".strip())
        elif role == "tool":
            lines.append(f"tool: {str(content)[:300]}")
        else:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def eligible_records(session: Session) -> list[MessageRecord]:
    """待压缩消息 = 未归档消息中，除最近 COMPRESS_KEEP_RECENT 轮以外的部分。"""
    active = session.active_messages
    keep = settings.compress_keep_recent
    boundary = len(active)
    seen_users = 0
    for i in range(len(active) - 1, -1, -1):
        if active[i].data.get("role") == "user":
            seen_users += 1
            if seen_users >= keep:
                boundary = i
                break
    else:
        return []
    return active[:boundary]


async def compress(session: Session, store: SessionStore) -> tuple[bool, str]:
    """执行一次压缩。返回 (是否压缩, 摘要或原因)。"""
    records = eligible_records(session)
    if not records:
        return False, "没有可压缩的历史消息"

    user_prompt = ""
    if session.summary:
        user_prompt += f"「既有摘要」\n{session.summary}\n\n"
    user_prompt += f"「对话历史」\n{_render(records)}"

    summary = await llm.complete(
        [
            {"role": "system", "content": _SUMMARIZE_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
    session.summary = summary.strip()
    session.turns_since_compress = 0
    await store.archive_messages(session, up_to_seq=records[-1].seq)
    await store.update_meta(session)
    return True, session.summary
