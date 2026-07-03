"""search 工具：mock 实现，返回构造的搜索结果。"""

import hashlib

from pydantic import BaseModel, Field

from app.tools.registry import tool

_FAKE_SITES = [
    ("wiki.example.com", "百科"),
    ("news.example.com", "新闻"),
    ("blog.example.com", "博客"),
]


class SearchParams(BaseModel):
    query: str = Field(description="The search query keywords.")
    top_k: int = Field(default=3, ge=1, le=5, description="Number of results to return.")


@tool(
    name="search",
    description="Search the web for up-to-date or external information. "
    "Returns a list of results with title, url and snippet. (Mock implementation.)",
    params=SearchParams,
)
async def search(params: SearchParams) -> str:
    # mock：基于 query 的稳定散列生成可复现的假结果
    seed = int(hashlib.md5(params.query.encode()).hexdigest(), 16)
    lines = []
    for i in range(params.top_k):
        site, kind = _FAKE_SITES[(seed + i) % len(_FAKE_SITES)]
        lines.append(
            f"[{i + 1}] {kind}: 关于「{params.query}」的{kind}条目\n"
            f"    url: https://{site}/{abs(seed + i) % 10000}\n"
            f"    snippet: 这是与「{params.query}」相关的模拟搜索结果摘要（第 {i + 1} 条），"
            f"内容仅用于演示 search 工具的调用链路。"
        )
    return "\n".join(lines)
