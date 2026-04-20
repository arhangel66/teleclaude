import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers import _build_prompt


def _bare_message(chat_id: int = 42) -> MagicMock:
    msg = MagicMock()
    msg.chat.id = chat_id
    msg.text = None
    msg.caption = None
    msg.photo = None
    msg.voice = None
    msg.video = None
    msg.video_note = None
    msg.animation = None
    msg.audio = None
    msg.sticker = None
    msg.document = None
    msg.forward_origin = None
    msg.location = None
    msg.venue = None
    msg.contact = None
    msg.poll = None
    msg.dice = None
    msg.reply_to_message = None
    return msg


@pytest.fixture
def tmp_files_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("src.bot.handlers.FILES_DIR", tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_plain_text_prompt_is_just_text() -> None:
    # Arrange
    message = _bare_message()
    message.text = "hello"

    # Act
    prompt = await _build_prompt(message)

    # Assert
    assert prompt == "hello"


@pytest.mark.asyncio
async def test_empty_message_returns_none() -> None:
    # Arrange
    message = _bare_message()

    # Act
    prompt = await _build_prompt(message)

    # Assert
    assert prompt is None


@pytest.mark.asyncio
async def test_forwarded_text_includes_metadata_json() -> None:
    # Arrange
    message = _bare_message()
    message.text = "fwd body"
    origin = MagicMock()
    origin.model_dump.return_value = {"type": "channel", "chat": {"id": -1, "title": "News"}}
    message.forward_origin = origin

    # Act
    prompt = await _build_prompt(message)

    # Assert
    assert prompt is not None
    assert "fwd body" in prompt
    assert "[Telegram context]" in prompt
    # JSON portion parses cleanly
    json_part = prompt.split("[Telegram context]\n", 1)[1]
    assert json.loads(json_part)["forward_origin"]["type"] == "channel"


@pytest.mark.asyncio
async def test_location_only_still_produces_prompt() -> None:
    # Arrange
    message = _bare_message()
    loc = MagicMock()
    loc.model_dump.return_value = {"latitude": 1.0, "longitude": 2.0}
    message.location = loc

    # Act
    prompt = await _build_prompt(message)

    # Assert
    assert prompt is not None
    assert "[Telegram context]" in prompt
    assert '"latitude": 1.0' in prompt


@pytest.mark.asyncio
async def test_photo_with_caption_and_reply(tmp_files_dir: Path) -> None:
    # Arrange
    message = _bare_message()
    message.caption = "nice"
    photo = MagicMock()
    photo.file_id = "pid"
    message.photo = [photo]
    reply = MagicMock()
    reply.message_id = 5
    reply.text = "earlier"
    reply.caption = None
    reply.from_user.username = "eve"
    message.reply_to_message = reply

    mock_bot = AsyncMock()

    # Act
    with patch("src.bot.handlers.bot", mock_bot):
        prompt = await _build_prompt(message)

    # Assert
    assert prompt is not None
    assert "nice" in prompt
    assert "[Files]" in prompt
    assert "(photo)" in prompt
    assert '"reply_to"' in prompt
