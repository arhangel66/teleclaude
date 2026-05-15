import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.bot.services.agent_runner import AgentRunner, STREAM_LIMIT_BYTES


class _Parser:
    def parse(self, data: dict[str, Any]) -> list[Any]:
        return []

    def finalize(self) -> list[Any]:
        return []


class _Backend:
    name = "test"

    def build_command(self, message: str, session_id: str | None = None) -> list[str]:
        return ["test-binary", message]

    def create_parser(self) -> _Parser:
        return _Parser()


@pytest.mark.asyncio
async def test_runner_uses_large_stdout_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    captured_kwargs: dict[str, Any] = {}
    proc = AsyncMock()
    proc.stdout = asyncio.StreamReader()
    proc.stdout.feed_eof()
    proc.stderr = asyncio.StreamReader()
    proc.returncode = 0

    async def fake_create_subprocess_exec(*_args: str, **kwargs: Any) -> Any:
        captured_kwargs.update(kwargs)
        return proc

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )
    runner = AgentRunner(_Backend(), working_directory="/tmp")

    # Act
    events = [event async for event in runner.run("hello", chat_id=1)]

    # Assert
    assert events == []
    assert captured_kwargs["limit"] == STREAM_LIMIT_BYTES
