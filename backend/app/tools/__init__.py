"""导入各工具模块以触发注册。"""

from app.tools import calculator, memory, read_docs, search  # noqa: F401
from app.tools.registry import registry  # noqa: F401
