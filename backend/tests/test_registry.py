import app.tools  # noqa: F401 - 触发注册
from app.tools.registry import registry


def test_all_tools_registered():
    assert set(registry.names()) == {"calculator", "search", "read_docs", "save_memory"}


def test_tools_schema_shape():
    schema = registry.get_tools_schema()
    assert len(schema) == 4
    for item in schema:
        assert item["type"] == "function"
        fn = item["function"]
        assert fn["name"] and fn["description"]
        assert fn["parameters"]["type"] == "object"


async def test_dispatch_calculator():
    result, ok = await registry.dispatch("calculator", '{"expression": "(3 + 5) * 2"}')
    assert ok
    assert result == "16"


async def test_dispatch_calculator_functions():
    result, ok = await registry.dispatch("calculator", '{"expression": "sqrt(16) + pi - pi"}')
    assert ok
    assert result == "4"


async def test_calculator_rejects_unsafe_expression():
    result, ok = await registry.dispatch(
        "calculator", '{"expression": "__import__(\'os\').getcwd()"}'
    )
    assert not ok
    assert "Error" in result


async def test_dispatch_unknown_tool():
    result, ok = await registry.dispatch("nope", "{}")
    assert not ok
    assert "unknown tool" in result


async def test_dispatch_invalid_json_arguments():
    result, ok = await registry.dispatch("calculator", "{not json")
    assert not ok
    assert "not valid JSON" in result


async def test_dispatch_invalid_params():
    result, ok = await registry.dispatch("calculator", '{"wrong_field": 1}')
    assert not ok
    assert "invalid arguments" in result


async def test_search_is_deterministic():
    r1, ok1 = await registry.dispatch("search", '{"query": "python asyncio"}')
    r2, ok2 = await registry.dispatch("search", '{"query": "python asyncio"}')
    assert ok1 and ok2 and r1 == r2


async def test_read_docs_list_and_read(tmp_env):
    from app.config import settings

    (settings.docs_dir / "guide.md").write_text("# Guide\nhello", encoding="utf-8")
    listing, ok = await registry.dispatch("read_docs", "{}")
    assert ok and "guide.md" in listing
    content, ok = await registry.dispatch("read_docs", '{"doc_name": "guide.md"}')
    assert ok and "hello" in content
    err, ok = await registry.dispatch("read_docs", '{"doc_name": "../secret.md"}')
    assert not ok or "Error" in err


async def test_save_memory_appends_and_dedupes(tmp_env):
    from app.config import settings
    from app.tools.memory import load_memory

    r, ok = await registry.dispatch("save_memory", '{"fact": "用户偏好中文回答"}')
    assert ok and "用户偏好中文回答" in load_memory()
    r2, _ = await registry.dispatch("save_memory", '{"fact": "用户偏好中文回答"}')
    assert "Already" in r2
    assert load_memory().count("用户偏好中文回答") == 1
