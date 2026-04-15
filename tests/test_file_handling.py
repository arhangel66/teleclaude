from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers import _download_file


@pytest.fixture
def tmp_files_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("src.bot.handlers.FILES_DIR", tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_download_photo_saves_file(tmp_files_dir: Path) -> None:
    """Smoke test: send photo, verify file path is returned."""
    # Arrange
    photo = MagicMock()
    photo.file_id = "abc123"

    message = MagicMock()
    message.chat.id = 42
    message.photo = [photo]
    message.voice = None
    message.video = None
    message.video_note = None
    message.document = None
    message.caption = "Look at this"

    mock_bot = AsyncMock()
    mock_bot.download = AsyncMock()

    # Act
    with patch("src.bot.handlers.bot", mock_bot):
        result = await _download_file(message)

    # Assert
    assert result is not None
    file_path, caption, kind = result
    assert caption == "Look at this"
    assert kind == "photo"
    assert str(file_path).endswith(".jpg")
    assert "/42/" in str(file_path)
    mock_bot.download.assert_called_once()


@pytest.mark.asyncio
async def test_download_returns_none_for_text_only() -> None:
    """No file in message -> returns None."""
    # Arrange
    message = MagicMock()
    message.chat.id = 42
    message.photo = None
    message.voice = None
    message.video = None
    message.video_note = None
    message.document = None

    # Act
    result = await _download_file(message)

    # Assert
    assert result is None
