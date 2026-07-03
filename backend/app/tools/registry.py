"""工具注册机制：装饰器注册 + JSON Schema 生成 + 统一调度。

每个工具 = 名称 + 描述 + pydantic 参数模型 + async handler。
LLM 侧只看到由参数模型自动生成的 JSON Schema，自主决策调用。
"""

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError

ToolHandler = Callable[[BaseModel], Awaitable[str]]


@dataclass
class ToolSpec:
    name: str
    description: str
    params_model: type[BaseModel]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name!r} already registered")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """生成 OpenAI 兼容的 tools 参数。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.params_model.model_json_schema(),
                },
            }
            for spec in self._tools.values()
        ]

    async def dispatch(self, name: str, arguments_json: str) -> tuple[str, bool]:
        """执行工具调用，返回 (结果字符串, 是否成功)。

        所有失败（未知工具/参数非法/执行异常）都转成错误文本交还模型，
        由模型决定重试或改口，不中断 agent loop。
        """
        spec = self._tools.get(name)
        if spec is None:
            return f"Error: unknown tool {name!r}. Available: {self.names()}", False
        try:
            raw = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as e:
            return f"Error: tool arguments is not valid JSON: {e}", False
        try:
            params = spec.params_model.model_validate(raw)
        except ValidationError as e:
            return f"Error: invalid arguments for {name}: {e}", False
        try:
            return await spec.handler(params), True
        except Exception as e:  # noqa: BLE001 - 工具内部错误一律回传模型
            return f"Error: tool {name} failed: {e}", False


registry = ToolRegistry()


def tool(name: str, description: str, params: type[BaseModel]):
    """把 async 函数注册为工具。handler 接收已校验的参数模型实例，返回字符串。"""

    def decorator(fn: ToolHandler) -> ToolHandler:
        registry.register(ToolSpec(name, description, params, fn))
        return fn

    return decorator
