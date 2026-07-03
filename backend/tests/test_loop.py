import json

import app.tools  # noqa: F401 - 触发注册
from app.agent import loop as loop_module
from app.agent.loop import AgentLoop
from app.config import settings
from app.sessions.store import SessionStore
from tests.conftest import FakeLLM, chunk, tool_call_chunk


async def _run(fake, message="hi"):
    store = SessionStore()
    session = await store.create()
    agent = AgentLoop(session, store)
    events = [e async for e in agent.run_turn(message, [])]
    return session, events, store


def _events_of(events, name):
    return [e for e in events if e.EVENT == name]


async def test_direct_answer(db, monkeypatch):
    fake = FakeLLM(
        [[chunk(reasoning="想一"), chunk(reasoning="想"), chunk(content="你"), chunk(content="好")]]
    )
    monkeypatch.setattr(loop_module, "llm", fake)

    session, events, _ = await _run(fake)

    starts = _events_of(events, "block_start")
    assert [b.block_type for b in starts] == ["reasoning", "text"]
    # 每个块都有配对的 end
    assert {b.block_id for b in starts} == {b.block_id for b in _events_of(events, "block_end")}
    assert len(fake.calls) == 1
    # 消息落库：user + assistant；reasoning 留存但 context 组装时剥离
    roles = [m.data["role"] for m in session.messages]
    assert roles == ["user", "assistant"]
    assert session.messages[1].data["content"] == "你好"
    assert session.messages[1].data["reasoning"] == "想一想"
    assert events[-1].EVENT == "done" and events[-1].turn_count == 1


async def test_tool_call_then_answer(db, monkeypatch):
    fake = FakeLLM(
        [
            [
                tool_call_chunk(0, id="call_1", name="calculator", arguments='{"expressi'),
                tool_call_chunk(0, arguments='on": "3*7"}'),
            ],
            [chunk(content="答案是 21")],
        ]
    )
    monkeypatch.setattr(loop_module, "llm", fake)

    session, events, _ = await _run(fake, "3*7 等于几")

    tool_starts = [e for e in _events_of(events, "block_start") if e.block_type == "tool"]
    assert len(tool_starts) == 1 and tool_starts[0].tool_name == "calculator"
    tool_ends = [e for e in _events_of(events, "block_end") if e.result is not None]
    assert tool_ends[0].status == "ok"
    assert tool_ends[0].result == "21"
    assert tool_ends[0].arguments == {"expression": "3*7"}

    # 第二次请求的 messages 应包含 assistant tool_calls + tool 结果
    second_messages = fake.calls[1]["messages"]
    assert second_messages[-1]["role"] == "tool"
    assert second_messages[-1]["content"] == "21"
    assert second_messages[-2]["tool_calls"][0]["function"]["name"] == "calculator"

    roles = [m.data["role"] for m in session.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]


async def test_tool_error_fed_back(db, monkeypatch):
    fake = FakeLLM(
        [
            [tool_call_chunk(0, id="c1", name="calculator", arguments='{"expression": "x+1"}')],
            [chunk(content="表达式无效")],
        ]
    )
    monkeypatch.setattr(loop_module, "llm", fake)

    session, events, _ = await _run(fake)
    tool_ends = [e for e in _events_of(events, "block_end") if e.result is not None]
    assert tool_ends[0].status == "error"
    assert "Error" in tool_ends[0].result
    assert events[-1].EVENT == "done"


async def test_max_iterations_forces_final_answer(db, monkeypatch):
    def tool_completion(i):
        return [
            tool_call_chunk(0, id=f"c{i}", name="calculator", arguments='{"expression": "1+1"}')
        ]

    fake = FakeLLM([tool_completion(i) for i in range(settings.max_iterations)])
    monkeypatch.setattr(loop_module, "llm", fake)

    session, events, _ = await _run(fake)

    assert len(fake.calls) == settings.max_iterations
    # 最后一轮迭代应强制 tool_choice="none"
    assert fake.calls[-1]["tool_choice"] == "none"
    assert all(c["tool_choice"] is None for c in fake.calls[:-1])
    assert events[-1].EVENT == "done"


async def test_session_isolation_and_rebuild(db, monkeypatch):
    fake = FakeLLM([[chunk(content="A 收到")], [chunk(content="B 收到")]])
    monkeypatch.setattr(loop_module, "llm", fake)

    store = SessionStore()
    s1 = await store.create()
    s2 = await store.create()
    [e async for e in AgentLoop(s1, store).run_turn("给 A 的消息", [])]
    [e async for e in AgentLoop(s2, store).run_turn("给 B 的消息", [])]

    assert [m.data["content"] for m in s1.messages] == ["给 A 的消息", "A 收到"]
    assert [m.data["content"] for m in s2.messages] == ["给 B 的消息", "B 收到"]

    # 模拟重启：新 store（缓存为空）从 SQLite 重建
    fresh = SessionStore()
    rebuilt = await fresh.get(s1.id)
    assert rebuilt is not None
    assert [m.data["content"] for m in rebuilt.messages] == ["给 A 的消息", "A 收到"]
    assert rebuilt.turn_count == 1


async def test_auto_compress_triggered(db, monkeypatch):
    monkeypatch.setattr(settings, "max_turns", 2)
    monkeypatch.setattr(settings, "compress_keep_recent", 1)

    fake = FakeLLM([[chunk(content=f"回复{i}")] for i in range(2)])
    monkeypatch.setattr(loop_module, "llm", fake)

    async def fake_complete(messages):
        return "这是压缩摘要"

    from app.llm import llm as llm_singleton

    monkeypatch.setattr(llm_singleton, "complete", fake_complete)

    store = SessionStore()
    session = await store.create()
    e1 = [e async for e in AgentLoop(session, store).run_turn("第一轮", [])]
    assert e1[-1].compressed is False
    e2 = [e async for e in AgentLoop(session, store).run_turn("第二轮", [])]
    assert e2[-1].compressed is True
    assert session.summary == "这是压缩摘要"
    assert session.turns_since_compress == 0
    # 除最近 compress_keep_recent 轮外的消息被归档
    archived = [m for m in session.messages if m.archived]
    assert archived and all(m.seq <= 1 for m in archived)
