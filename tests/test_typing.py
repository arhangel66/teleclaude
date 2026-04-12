import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.services.telegram_ui import TelegramUI, TYPING_INTERVAL_SECONDS


@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()
    return bot


@pytest.fixture
def ui(mock_bot: MagicMock) -> TelegramUI:
    return TelegramUI(bot=mock_bot)


@pytest.mark.asyncio
async def test_typing_loop_sends_action_at_interval(ui: TelegramUI, mock_bot: MagicMock) -> None:
    """Typing loop sends chat action immediately and repeats at interval."""
    # Arrange
    chat_id = 123

    # Act
    await ui.start_typing(chat_id)
    await asyncio.sleep(TYPING_INTERVAL_SECONDS + 0.5)
    await ui.stop_typing(chat_id)

    # Assert — at least 2 calls: one immediately, one after interval
    assert mock_bot.send_chat_action.call_count >= 2
    mock_bot.send_chat_action.assert_any_call(chat_id=chat_id, action="typing")


@pytest.mark.asyncio
async def test_stop_typing_cancels_background_task(ui: TelegramUI, mock_bot: MagicMock) -> None:
    """stop_typing cancels the background task and cleans up."""
    # Arrange
    chat_id = 456
    await ui.start_typing(chat_id)
    task = ui._typing_tasks.get(chat_id)
    assert task is not None

    # Act
    await ui.stop_typing(chat_id)

    # Assert
    assert task.cancelled() or task.done()
    assert chat_id not in ui._typing_tasks


@pytest.mark.asyncio
async def test_typing_cleanup_on_handler_error(ui: TelegramUI, mock_bot: MagicMock) -> None:
    """Typing is stopped even when processing raises an exception."""
    # Arrange
    chat_id = 789
    await ui.start_typing(chat_id)
    assert chat_id in ui._typing_tasks

    # Act — simulate handler error with finally cleanup
    try:
        raise RuntimeError("simulated processing error")
    except RuntimeError:
        pass
    finally:
        await ui.stop_typing(chat_id)

    # Assert
    assert chat_id not in ui._typing_tasks
    task = ui._typing_tasks.get(chat_id)
    assert task is None
