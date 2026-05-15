from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.services.runner_events import ResultEvent, SystemEvent, TextEvent
from src.bot.services.task_runner import run_prompt


@pytest.mark.asyncio
async def test_run_prompt_uses_selected_backend_session_and_renderer() -> None:
    # Arrange
    async def fake_run(message: str, chat_id: int, session_id: str | None = None):
        assert message == "hello"
        assert chat_id == 42
        assert session_id == "thread-1"
        yield SystemEvent(session_id="thread-2")
        yield TextEvent(text="stream")
        yield ResultEvent(text="done", context_tokens=123)

    runner = MagicMock()
    runner.backend_name = "codex"
    runner.run = fake_run
    session_store = MagicMock()
    session_store.get = AsyncMock(return_value="thread-1")
    session_store.set = AsyncMock()
    ui = MagicMock()
    ui.start_typing = AsyncMock()
    ui.stop_typing = AsyncMock()
    ui.send_final = AsyncMock()
    renderer = MagicMock()
    renderer.on_text = AsyncMock()
    renderer.on_final = AsyncMock()

    # Act
    await run_prompt(
        chat_id=42,
        prompt="hello",
        claude_runner=runner,
        session_store=session_store,
        ui=ui,
        renderer=renderer,
    )

    # Assert
    session_store.get.assert_awaited_once_with(42, backend="codex")
    session_store.set.assert_awaited_once_with(
        42, "thread-2", backend="codex"
    )
    renderer.on_text.assert_awaited_once_with("stream")
    renderer.on_final.assert_awaited_once_with("done", 123)
    ui.send_final.assert_not_awaited()
