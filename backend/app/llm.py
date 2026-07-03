"""DashScope OpenAI 兼容接口封装。

注意事项（来自 DashScope 文档）：
- enable_thinking 需经 extra_body 传入，思考内容在 delta.reasoning_content；
- 思考模型基本只支持流式，因此统一 stream=True，非流式需求由 complete() 聚合。
"""

from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from app.config import settings


class LLMClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.alibaba_api_key, base_url=settings.alibaba_base_url
        )

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        enable_thinking: bool | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[Any]:
        if enable_thinking is None:
            enable_thinking = settings.enable_thinking
        kwargs: dict[str, Any] = {
            "model": settings.alibaba_model_name,
            "messages": messages,
            "stream": True,
            "extra_body": {"enable_thinking": enable_thinking},
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        return await self._client.chat.completions.create(**kwargs)

    async def complete(self, messages: list[dict[str, Any]]) -> str:
        """无工具、关思考的一次性补全（聚合流式输出），用于总结压缩。"""
        stream = await self.stream_chat(messages, enable_thinking=False)
        parts: list[str] = []
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                parts.append(delta.content)
        return "".join(parts)


llm = LLMClient()
