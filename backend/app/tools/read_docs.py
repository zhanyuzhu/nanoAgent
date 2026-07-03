"""read_docs 工具：列出/读取 docs_store/ 下的本地文档。"""

from pydantic import BaseModel, Field

from app.config import settings
from app.tools.registry import tool


class ReadDocsParams(BaseModel):
    doc_name: str | None = Field(
        default=None,
        description="Document file name to read (e.g. 'agent-design.md'). "
        "Omit to list all available documents.",
    )


@tool(
    name="read_docs",
    description="Read project documentation. Call without doc_name to list available "
    "documents first, then call again with a doc_name to read its content.",
    params=ReadDocsParams,
)
async def read_docs(params: ReadDocsParams) -> str:
    docs_dir = settings.docs_dir.resolve()
    if params.doc_name is None:
        docs = sorted(p.name for p in docs_dir.glob("*.md"))
        if not docs:
            return "No documents available."
        return "Available documents:\n" + "\n".join(f"- {d}" for d in docs)

    target = (docs_dir / params.doc_name).resolve()
    # 防路径穿越：解析后必须仍在 docs_dir 内
    if not target.is_relative_to(docs_dir):
        return f"Error: invalid doc_name {params.doc_name!r}"
    if not target.is_file():
        docs = sorted(p.name for p in docs_dir.glob("*.md"))
        return f"Error: document {params.doc_name!r} not found. Available: {docs}"
    return target.read_text(encoding="utf-8")
