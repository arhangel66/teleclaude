import base64
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TRANSCRIBE_PROMPT = (
    "Transcribe this audio in its original language. "
    "Return only the transcript text, no prefix, no commentary."
)
REQUEST_TIMEOUT_SECONDS = 60.0

_FORMAT_BY_SUFFIX = {
    ".ogg": "ogg",
    ".oga": "ogg",
    ".mp3": "mp3",
    ".wav": "wav",
    ".m4a": "m4a",
    ".aac": "aac",
    ".flac": "flac",
    ".mp4": "mp4",
}


class TranscriptionError(RuntimeError):
    pass


class Transcriber:
    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def transcribe(self, audio_path: Path) -> str:
        audio_format = _FORMAT_BY_SUFFIX.get(audio_path.suffix.lower())
        if audio_format is None:
            raise TranscriptionError(f"unsupported audio format: {audio_path.suffix}")

        data = audio_path.read_bytes()
        if not data:
            raise TranscriptionError("audio file is empty")
        encoded = base64.b64encode(data).decode("ascii")

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": TRANSCRIBE_PROMPT},
                        {
                            "type": "input_audio",
                            "input_audio": {"data": encoded, "format": audio_format},
                        },
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.post(OPENROUTER_URL, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                raise TranscriptionError(f"HTTP error: {exc}") from exc

        if response.status_code >= 400:
            raise TranscriptionError(
                f"OpenRouter returned {response.status_code}: {response.text[:300]}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise TranscriptionError(f"invalid JSON from OpenRouter: {exc}") from exc

        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TranscriptionError(f"unexpected response shape: {body}") from exc

        if not isinstance(text, str) or not text.strip():
            raise TranscriptionError("empty transcript from OpenRouter")

        return text.strip()
