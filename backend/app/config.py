from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    alibaba_model_name: str = "qwen3-vl-plus"
    alibaba_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    alibaba_api_key: str = ""

    enable_thinking: bool = True
    # 单次请求内工具调用循环上限
    max_iterations: int = 8
    # 距上次压缩满多少轮后自动触发总结压缩
    max_turns: int = 10
    # context 组装时保留的最近对话轮数（1 轮 = user → 最终 assistant）
    recent_keep: int = 4
    # 压缩时保留原文的最近轮数，其余进摘要
    compress_keep_recent: int = 2

    data_dir: Path = BASE_DIR / "data"
    docs_dir: Path = BASE_DIR / "docs_store"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "agent.db"

    @property
    def memory_path(self) -> Path:
        return self.data_dir / "memory.md"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
