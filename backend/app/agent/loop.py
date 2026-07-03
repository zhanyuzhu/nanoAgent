"""核心 Agent Loop：接收输入 → LLM 决策 → 工具执行 → 循环或返回。

单个用户轮次内的流程：
1. user 消息入 session，组装 context；
2. 带 tools schema 流式请求 LLM，逐 delta 解析 reasoning / text / tool_calls 三路，
   实时转成块级 SSE 事件；
3. 有 tool_calls 则逐个 dispatch，结果以 tool 消息回填后继续迭代；
   无 tool_calls 则 content 即最终答案；
4. 迭代达到 max_iterations - 1 时最后一轮以 tool_choice="none" 强制直答；
5. 轮次结束更新计数，满 MAX_TURNS 自动触发总结压缩。
"""

import json
from typing import Any, AsyncIterator

from app.agent.events import BlockDelta, BlockEnd, BlockStart, Done, Event
from app.config import settings
from app.context.assembler import assemble, strip_for_context
from app.context.summarizer import compress
from app.llm import llm
from app.sessions.models import Session
from app.sessions.store import SessionStore
from app.tools.registry import registry


def build_user_content(message: str, images: list[str]) -> str | list[dict[str, Any]]:
    if not images:
        return message
    parts: list[dict[str, Any]] = [
        {"type": "image_url", "image_url": {"url": url}} for url in images
    ]
    parts.append({"type": "text", "text": message})
    return parts


class AgentLoop:
    def __init__(self, session: Session, store: SessionStore) -> None:
        self.session = session
        self.store = store
        self._block_counter = 0

    def _new_block_id(self) -> str:
        self._block_counter += 1
        return f"{self.session.turn_count}-{self._block_counter}"

    async def run_turn(self, message: str, images: list[str]) -> AsyncIterator[Event]:
        session, store = self.session, self.store
        await store.append_message(
            session, {"role": "user", "content": build_user_content(message, images)}
        )
        request_messages = assemble(session)
        tools = registry.get_tools_schema()

        for iteration in range(settings.max_iterations):
            force_answer = iteration == settings.max_iterations - 1
            out: dict[str, Any] = {}
            async for event in self._stream_one_completion(
                request_messages, tools, "none" if force_answer else None, out
            ):
                yield event

            assistant_data: dict[str, Any] = {"role": "assistant", "content": out["content"]}
            if out["reasoning"]:
                # 思考过程仅留存供展示，assemble 时会剥离，不回填 context
                assistant_data["reasoning"] = out["reasoning"]
            if out["tool_calls"]:
                assistant_data["tool_calls"] = [
                    {
                        "id": acc["id"],
                        "type": "function",
                        "function": {"name": acc["name"], "arguments": acc["arguments"]},
                    }
                    for acc in out["tool_calls"]
                ]
            await store.append_message(session, assistant_data)
            request_messages.append(strip_for_context(assistant_data))

            if not out["tool_calls"]:
                break

            for acc in out["tool_calls"]:
                result, ok = await registry.dispatch(acc["name"], acc["arguments"])
                try:
                    arguments = json.loads(acc["arguments"] or "{}")
                except json.JSONDecodeError:
                    arguments = {"_raw": acc["arguments"]}
                yield BlockEnd(
                    block_id=acc["block_id"],
                    tool_name=acc["name"],
                    arguments=arguments,
                    result=result,
                    status="ok" if ok else "error",
                )
                tool_message = {
                    "role": "tool",
                    "tool_call_id": acc["id"],
                    "content": result,
                }
                await store.append_message(session, tool_message)
                request_messages.append(tool_message)

        session.turn_count += 1
        session.turns_since_compress += 1
        await store.update_meta(session)

        compressed = False
        if session.turns_since_compress >= settings.max_turns:
            compressed, _ = await compress(session, store)
        yield Done(turn_count=session.turn_count, compressed=compressed)

    async def _stream_one_completion(
        self,
        request_messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | None,
        out: dict[str, Any],
    ) -> AsyncIterator[Event]:
        """流式请求一次 LLM 并解析 delta 三路输出。

        reasoning / text 块在此处完成 start→delta→end 生命周期；
        tool 块在此处 start + delta（arguments 增量），block_end 由调用方在
        工具执行完后携带 result 发出。
        聚合结果写入 out：{"reasoning", "content", "tool_calls"}。
        """
        stream = await llm.stream_chat(request_messages, tools=tools, tool_choice=tool_choice)

        current: tuple[str, str] | None = None  # 当前打开的 (block_id, type)
        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        tool_acc: dict[int, dict[str, str]] = {}  # tool_calls 按 index 归组累积

        def switch_block(block_type: str) -> list[Event]:
            nonlocal current
            events: list[Event] = []
            if current and current[1] != block_type:
                events.append(BlockEnd(block_id=current[0]))
                current = None
            if current is None:
                current = (self._new_block_id(), block_type)
                events.append(BlockStart(block_id=current[0], block_type=block_type))
            return events

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue

            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                for e in switch_block("reasoning"):
                    yield e
                reasoning_parts.append(reasoning)
                yield BlockDelta(block_id=current[0], delta=reasoning)

            if delta.content:
                for e in switch_block("text"):
                    yield e
                content_parts.append(delta.content)
                yield BlockDelta(block_id=current[0], delta=delta.content)

            for tc in delta.tool_calls or []:
                index = tc.index or 0
                acc = tool_acc.get(index)
                if acc is None:
                    # 首片：关闭打开中的 reasoning/text 块，开 tool 块
                    if current:
                        yield BlockEnd(block_id=current[0])
                        current = None
                    acc = tool_acc[index] = {
                        "block_id": self._new_block_id(),
                        "id": "",
                        "name": "",
                        "arguments": "",
                    }
                    yield BlockStart(
                        block_id=acc["block_id"],
                        block_type="tool",
                        tool_name=(tc.function.name if tc.function else None),
                    )
                if tc.id:
                    acc["id"] = acc["id"] or tc.id
                if tc.function:
                    if tc.function.name:
                        acc["name"] = acc["name"] or tc.function.name
                    if tc.function.arguments:
                        acc["arguments"] += tc.function.arguments
                        yield BlockDelta(block_id=acc["block_id"], delta=tc.function.arguments)

        if current:
            yield BlockEnd(block_id=current[0])

        out["reasoning"] = "".join(reasoning_parts)
        out["content"] = "".join(content_parts)
        out["tool_calls"] = [tool_acc[i] for i in sorted(tool_acc)]
