from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers import _download_file


def _bare_attachment_message(chat_id: int = 42) -> MagicMock:
    msg = MagicMock()
    msg.chat.id = chat_id
    msg.photo = None
    msg.voice = None
    msg.video = None
    msg.video_note = None
    msg.animation = None
    msg.audio = None
    msg.sticker = None
    msg.document = None
    msg.caption = None
    return msg


@pytest.fixture
def tmp_files_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("src.bot.handlers.FILES_DIR", tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_download_animation(tmp_files_dir: Path) -> None:
    # Arrange
    message = _bare_attachment_message()
    animation = MagicMock()
    animation.file_id = "anim1"
    message.animation = animation
    mock_bot = AsyncMock()

    # Act
    with patch("src.bot.handlers.bot", mock_bot):
        result = await _download_file(message)

    # Assert
    assert result is not None
    path, _caption, kind = result
    assert kind == "animation"
    assert str(path).endswith(".mp4")


@pytest.mark.asyncio
async def test_download_audio_preserves_name(tmp_files_dir: Path) -> None:
    # Arrange
    message = _bare_attachment_message()
    audio = MagicMock()
    audio.file_id = "aud1"
    audio.file_name = "song.mp3"
    message.audio = audio
    mock_bot = AsyncMock()

    # Act
    with patch("src.bot.handlers.bot", mock_bot):
        result = await _download_file(message)

    # Assert
    assert result is not None
    path, _caption, kind = result
    assert kind == "audio"
    assert str(path).endswith("song.mp3")


@pytest.mark.asyncio
async def test_download_static_sticker_uses_webp(tmp_files_dir: Path) -> None:
    # Arrange
    message = _bare_attachment_message()
    sticker = MagicMock()
    sticker.file_id = "stk1"
    sticker.is_animated = False
    sticker.is_video = False
    message.sticker = sticker
    mock_bot = AsyncMock()

    # Act
    with patch("src.bot.handlers.bot", mock_bot):
        result = await _download_file(message)

    # Assert
    assert result is not None
    path, _caption, kind = result
    assert kind == "sticker"
    assert str(path).endswith(".webp")


@pytest.mark.asyncio
async def test_download_animated_sticker_uses_tgs(tmp_files_dir: Path) -> None:
    # Arrange
    message = _bare_attachment_message()
    sticker = MagicMock()
    sticker.file_id = "stk2"
    sticker.is_animated = True
    sticker.is_video = False
    message.sticker = sticker
    mock_bot = AsyncMock()

    # Act
    with patch("src.bot.handlers.bot", mock_bot):
        result = await _download_file(message)

    # Assert
    assert result is not None
    path, _caption, _kind = result
    assert str(path).endswith(".tgs")


@pytest.mark.asyncio
async def test_download_video_sticker_uses_webm(tmp_files_dir: Path) -> None:
    # Arrange
    message = _bare_attachment_message()
    sticker = MagicMock()
    sticker.file_id = "stk3"
    sticker.is_animated = False
    sticker.is_video = True
    message.sticker = sticker
    mock_bot = AsyncMock()

    # Act
    with patch("src.bot.handlers.bot", mock_bot):
        result = await _download_file(message)

    # Assert
    assert result is not None
    path, _caption, _kind = result
    assert str(path).endswith(".webm")
