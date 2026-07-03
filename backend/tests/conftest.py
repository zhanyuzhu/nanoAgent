from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.config import settings


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    """把 data/docs 目录指向临时目录，避免测试污染真实数据。"""
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    data_dir.mkdir()
    docs_dir.mkdir()
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "docs_dir", docs_dir)
    return tmp_path


@pytest_asyncio.fixture
async def db(tmp_env):
    """每个测试用独立的临时 SQLite。"""
    from app.sessions.db import close_db

    await close_db()
    yield
    await close_db()


def chunk(content=None, reasoning=None, tool_calls=None):
    """构造一个模拟 openai 流式 chunk。"""
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    if reasoning is not None:
        delta.reasoning_content = reasoning
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def tool_call_chunk(index=0, id=None, name=None, arguments=None):
    tc = SimpleNamespace(
        index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments)
    )
    return chunk(tool_calls=[tc])


class FakeLLM:
    """按预设脚本依次返回各次 completion 的 chunk 序列。"""

    def __init__(self, completions):
        self.completions = list(completions)
        self.calls = []

    async def stream_chat(self, messages, tools=None, enable_thinking=None, tool_choice=None):
        self.calls.append(
            {"messages": list(messages), "tools": tools, "tool_choice": tool_choice}
        )
        chunks = self.completions.pop(0)

        async def gen():
            for c in chunks:
                yield c

        return gen()
