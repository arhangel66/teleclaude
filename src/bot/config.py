from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    telegram_bot_token: str
    allowed_chat_ids: list[int]
    working_directory: str
    agent_backend: Literal["claude", "codex"] = "claude"
    claude_binary: str = "claude"
    codex_binary: str = "codex"
    sqlite_db: str = "sessions.db"

    openrouter_api_key: str = ""
    stt_model: str = "google/gemini-3-flash-preview"
    streaming_mode: Literal["verbose", "compact", "quiet", "thread"] = "thread"
    file_retention_days: int = 7

    @field_validator("allowed_chat_ids", mode="before")
    @classmethod
    def parse_chat_ids(cls, v: str | int | list[int]) -> list[int]:
        if isinstance(v, int):
            return [v]
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v
