import base64
from pathlib import Path

import httpx
import pytest

from src.bot.services.transcriber import (
    OPENROUTER_URL,
    Transcriber,
    TranscriptionError,
)


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    p = tmp_path / "voice.ogg"
    p.write_bytes(b"\x00\x01\x02fake-audio")
    return p


def _build_client_factory(handler):
    class _DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            return handler(url, json, headers)

    return _DummyClient


@pytest.mark.asyncio
async def test_transcribe_success(
    audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    seen: dict[str, object] = {}

    def handler(url, json, headers):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        return httpx.Response(
            status_code=200,
            json={"choices": [{"message": {"content": "hello world"}}]},
        )

    monkeypatch.setattr(
        "src.bot.services.transcriber.httpx.AsyncClient", _build_client_factory(handler)
    )
    t = Transcriber(api_key="test-key", model="google/gemini-2.5-flash")

    # Act
    result = await t.transcribe(audio_file)

    # Assert
    assert result == "hello world"
    assert seen["url"] == OPENROUTER_URL
    assert seen["headers"]["Authorization"] == "Bearer test-key"
    body = seen["json"]
    assert body["model"] == "google/gemini-2.5-flash"
    audio_block = body["messages"][0]["content"][1]
    assert audio_block["type"] == "input_audio"
    assert audio_block["input_audio"]["format"] == "ogg"
    expected_b64 = base64.b64encode(audio_file.read_bytes()).decode("ascii")
    assert audio_block["input_audio"]["data"] == expected_b64


@pytest.mark.asyncio
async def test_transcribe_http_error_raises(
    audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    def handler(url, json, headers):
        return httpx.Response(status_code=500, text="server down")

    monkeypatch.setattr(
        "src.bot.services.transcriber.httpx.AsyncClient", _build_client_factory(handler)
    )
    t = Transcriber(api_key="k", model="m")

    # Act / Assert
    with pytest.raises(TranscriptionError) as exc_info:
        await t.transcribe(audio_file)
    assert "500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_transcribe_empty_content_raises(
    audio_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    def handler(url, json, headers):
        return httpx.Response(
            status_code=200, json={"choices": [{"message": {"content": "   "}}]}
        )

    monkeypatch.setattr(
        "src.bot.services.transcriber.httpx.AsyncClient", _build_client_factory(handler)
    )
    t = Transcriber(api_key="k", model="m")

    # Act / Assert
    with pytest.raises(TranscriptionError):
        await t.transcribe(audio_file)


@pytest.mark.asyncio
async def test_transcribe_unsupported_format_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    bad = tmp_path / "x.xyz"
    bad.write_bytes(b"data")
    t = Transcriber(api_key="k", model="m")

    # Act / Assert
    with pytest.raises(TranscriptionError):
        await t.transcribe(bad)


@pytest.mark.asyncio
async def test_transcribe_video_note_uses_mp4_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    video = tmp_path / "note.mp4"
    video.write_bytes(b"mp4-bytes")
    captured: dict[str, object] = {}

    def handler(url, json, headers):
        captured["json"] = json
        return httpx.Response(
            status_code=200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    monkeypatch.setattr(
        "src.bot.services.transcriber.httpx.AsyncClient", _build_client_factory(handler)
    )
    t = Transcriber(api_key="k", model="m")

    # Act
    result = await t.transcribe(video)

    # Assert
    assert result == "ok"
    block = captured["json"]["messages"][0]["content"][1]
    assert block["input_audio"]["format"] == "mp4"
