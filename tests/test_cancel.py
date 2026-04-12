import asyncio
from unittest.mock import MagicMock

import pytest

from src.bot.services.claude_runner import ClaudeRunner


@pytest.mark.asyncio
async def test_cancel_terminates_active_subprocess() -> None:
    """Smoke test: cancel kills running subprocess."""
    # Arrange
    runner = ClaudeRunner(claude_binary="claude", working_directory="/tmp")

    mock_proc = MagicMock()
    mock_proc.returncode = None  # still running
    mock_proc.terminate = MagicMock()

    runner._active[42] = mock_proc

    # Act
    result = await runner.cancel(42)

    # Assert
    assert result is True
    mock_proc.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_no_active_subprocess() -> None:
    """Cancel with no active subprocess does nothing."""
    # Arrange
    runner = ClaudeRunner(claude_binary="claude", working_directory="/tmp")

    # Act
    result = await runner.cancel(42)

    # Assert
    assert result is False


@pytest.mark.asyncio
async def test_cancel_already_finished() -> None:
    """Cancel after subprocess already finished returns False."""
    # Arrange
    runner = ClaudeRunner(claude_binary="claude", working_directory="/tmp")

    mock_proc = MagicMock()
    mock_proc.returncode = 0  # already finished

    runner._active[42] = mock_proc

    # Act
    result = await runner.cancel(42)

    # Assert
    assert result is False
    mock_proc.terminate.assert_not_called()
