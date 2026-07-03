from app.config import settings
from app.context.assembler import (
    assemble,
    build_system_prompt,
    strip_for_context,
    take_recent_turns,
)
from app.sessions.models import MessageRecord, Session


def _records(*roles):
    return [MessageRecord(seq=i, data={"role": r, "content": f"m{i}"}) for i, r in enumerate(roles)]


def test_take_recent_turns_starts_at_user():
    records = _records("user", "assistant", "user", "assistant", "tool", "user", "assistant")
    recent = take_recent_turns(records, 2)
    assert recent[0].data["role"] == "user"
    assert [m.seq for m in recent] == [2, 3, 4, 5, 6]


def test_take_recent_turns_fewer_than_k():
    records = _records("user", "assistant")
    assert len(take_recent_turns(records, 4)) == 2


def test_strip_removes_reasoning():
    data = {"role": "assistant", "content": "hi", "reasoning": "内心戏", "tool_calls": []}
    stripped = strip_for_context(data)
    assert "reasoning" not in stripped
    assert stripped["role"] == "assistant"


def test_system_prompt_layers(tmp_env):
    settings.memory_path.write_text("- 用户喜欢猫", encoding="utf-8")
    prompt = build_system_prompt(summary="用户之前问过天气")
    assert "长期记忆" in prompt and "用户喜欢猫" in prompt
    assert "早前对话摘要" in prompt and "用户之前问过天气" in prompt


def test_assemble_skips_archived(tmp_env, monkeypatch):
    monkeypatch.setattr(settings, "recent_keep", 2)
    session = Session(id="s1", summary="旧摘要")
    session.messages = _records("user", "assistant", "user", "assistant", "user", "assistant")
    session.messages[0].archived = True
    session.messages[1].archived = True
    messages = assemble(session)
    assert messages[0]["role"] == "system"
    assert "旧摘要" in messages[0]["content"]
    # 归档消息不进 context；recent_keep=2 → 取 seq 2..5
    assert [m["content"] for m in messages[1:]] == ["m2", "m3", "m4", "m5"]
