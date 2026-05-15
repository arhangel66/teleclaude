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


@pytest.mark.asyncio
async def test_run_prompt_compact_rebuilds_session() -> None:
    # Arrange
    calls: list[tuple[str, int, str | None]] = []

    async def fake_run(message: str, chat_id: int, session_id: str | None = None):
        calls.append((message, chat_id, session_id))
        if session_id == "thread-1":
            assert "/compact" not in message
            assert "context checkpoint compaction" in message
            yield ResultEvent(text="handoff summary", context_tokens=900)
            return

        assert session_id is None
        assert "[chat_id=42]" in message
        assert "handoff summary" in message
        yield SystemEvent(session_id="thread-2")
        yield ResultEvent(text="Context loaded.", context_tokens=120)

    runner = MagicMock()
    runner.backend_name = "codex"
    runner.run = fake_run
    session_store = MagicMock()
    session_store.get = AsyncMock(return_value="thread-1")
    session_store.reset = AsyncMock()
    session_store.set = AsyncMock()
    ui = MagicMock()
    ui.start_typing = AsyncMock()
    ui.stop_typing = AsyncMock()
    ui.send_final = AsyncMock()
    renderer = MagicMock()
    renderer.on_final = AsyncMock()
    renderer.cleanup = AsyncMock()

    # Act
    await run_prompt(
        chat_id=42,
        prompt="/compact",
        claude_runner=runner,
        session_store=session_store,
        ui=ui,
        renderer=renderer,
    )

    # Assert
    session_store.get.assert_awaited_once_with(42, backend="codex")
    session_store.reset.assert_not_awaited()
    session_store.set.assert_awaited_once_with(42, "thread-2", backend="codex")
    renderer.on_final.assert_awaited_once_with("Context compacted.", 0)
    ui.send_final.assert_not_awaited()
    assert len(calls) == 2
    assert calls[0][2] == "thread-1"
    assert calls[1][2] is None


@pytest.mark.asyncio
async def test_run_prompt_compact_without_session_reports_noop() -> None:
    # Arrange
    runner = MagicMock()
    runner.backend_name = "codex"
    runner.run = MagicMock()
    session_store = MagicMock()
    session_store.get = AsyncMock(return_value=None)
    session_store.reset = AsyncMock()
    session_store.set = AsyncMock()
    ui = MagicMock()
    ui.start_typing = AsyncMock()
    ui.stop_typing = AsyncMock()
    ui.send_text = AsyncMock()

    # Act
    await run_prompt(
        chat_id=42,
        prompt="/compact",
        claude_runner=runner,
        session_store=session_store,
        ui=ui,
        deliver="final",
        start_typing=False,
    )

    # Assert
    runner.run.assert_not_called()
    session_store.reset.assert_not_awaited()
    session_store.set.assert_not_awaited()
    ui.send_text.assert_awaited_once_with(42, "No active session to compact.")
