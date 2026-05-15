import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from aiogram import Router, types
from aiogram.filters import Command

from src.bot.construct import (
    agent_runner,
    bot,
    session_store,
    settings,
    telegram_ui,
    transcriber,
)
from src.bot.services.task_runner import run_prompt
from src.bot.services.telegram_ui import CANCEL_CALLBACK_PREFIX, build_renderer
from src.bot.services.transcriber import TranscriptionError

logger = logging.getLogger(__name__)
router = Router()

FILES_DIR = Path("files")

# Per-chat lock: messages from the same chat are processed one after another.
_chat_locks: dict[int, asyncio.Lock] = {}


def _chat_lock(chat_id: int) -> asyncio.Lock:
    lock = _chat_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _chat_locks[chat_id] = lock
    return lock

Attachment = tuple[Path, str]  # (absolute_path, kind)


def _sticker_extension(sticker: types.Sticker) -> str:
    if sticker.is_animated:
        return "tgs"
    if sticker.is_video:
        return "webm"
    return "webp"


def _pick_attachment(message: types.Message) -> tuple[str, str, str] | None:
    """Return (file_id, filename, kind) for the attachment, or None."""
    ts = int(time.time())

    if message.photo:
        largest = message.photo[-1]
        return largest.file_id, f"{ts}_{largest.file_id}.jpg", "photo"
    if message.voice:
        return message.voice.file_id, f"{ts}_voice.ogg", "voice"
    if getattr(message, "video_note", None):
        return message.video_note.file_id, f"{ts}_video_note.mp4", "video_note"
    if message.video:
        return message.video.file_id, f"{ts}_video.mp4", "video"
    if message.animation:
        return message.animation.file_id, f"{ts}_animation.mp4", "animation"
    if message.audio:
        name = message.audio.file_name or "audio.mp3"
        return message.audio.file_id, f"{ts}_{name}", "audio"
    if message.sticker:
        ext = _sticker_extension(message.sticker)
        return message.sticker.file_id, f"{ts}_sticker.{ext}", "sticker"
    if message.document:
        name = message.document.file_name or "document"
        return message.document.file_id, f"{ts}_{name}", "document"
    return None


async def _attach_or_none(message: types.Message) -> tuple[Attachment | None, str]:
    picked = _pick_attachment(message)
    caption = message.caption or ""
    if not picked:
        return None, caption

    file_id, filename, kind = picked
    dest_dir = FILES_DIR / str(message.chat.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename
    await bot.download(file_id, destination=dest_path)
    return (dest_path.resolve(), kind), caption


# Backwards-compatible helper used by existing tests.
async def _download_file(message: types.Message) -> tuple[Path, str, str] | None:
    attachment, caption = await _attach_or_none(message)
    if attachment is None:
        return None
    path, kind = attachment
    return path, caption, kind


def _extract_metadata(message: types.Message) -> dict[str, Any]:
    """Collect non-file Telegram context fields (forward info, location, etc.)."""
    meta: dict[str, Any] = {}

    def dump(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(exclude_none=True, mode="json")
        return value

    forward_origin = getattr(message, "forward_origin", None)
    if forward_origin is not None:
        meta["forward_origin"] = dump(forward_origin)

    for field in ("location", "venue", "contact", "poll", "dice"):
        value = getattr(message, field, None)
        if value is not None:
            meta[field] = dump(value)

    reply = message.reply_to_message
    if reply is not None:
        snippet = reply.text or reply.caption or ""
        sender = reply.from_user.username if reply.from_user else None
        meta["reply_to"] = {
            "message_id": reply.message_id,
            "from": sender,
            "text": snippet[:500],
        }

    return meta


def _is_allowed(chat_id: int) -> bool:
    return chat_id in settings.allowed_chat_ids


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    if not _is_allowed(message.chat.id):
        return
    await message.answer("CLI agent bridge is ready. Send me a message.")


@router.message(Command("new"))
async def cmd_new(message: types.Message) -> None:
    if not _is_allowed(message.chat.id):
        return
    await session_store.reset(message.chat.id, backend=agent_runner.backend_name)
    await message.answer("New session started.")


async def _build_prompt(message: types.Message) -> str | None:
    """Resolve the message into an agent prompt. Returns None if unusable."""
    attachment, caption = await _attach_or_none(message)
    metadata = _extract_metadata(message)
    text = message.text or caption or ""

    # Voice/video_note: transcribe and inline the text; do not pass the file path.
    if attachment is not None:
        path, kind = attachment
        if kind in ("voice", "video_note"):
            try:
                transcript = await transcriber.transcribe(path)
            except TranscriptionError as exc:
                logger.warning(
                    "Transcription failed for chat_id=%d: %s", message.chat.id, exc
                )
                await telegram_ui.send_text(
                    message.chat.id, f"Не удалось распознать речь: {exc}"
                )
                return None
            logger.info("Transcribed voice (%d chars)", len(transcript))
            text_part = f"(voice transcript): {transcript}"
            if caption:
                text_part = f"{text_part}\n\n{caption}"
            return _assemble_prompt(text_part, metadata, files=[])

    files: list[tuple[Path, str]] = []
    if attachment is not None:
        files.append(attachment)

    if not text and not metadata and not files:
        return None

    return _assemble_prompt(text, metadata, files)


def _assemble_prompt(
    text: str, metadata: dict[str, Any], files: list[tuple[Path, str]]
) -> str:
    parts: list[str] = []
    if text:
        parts.append(text)
    if metadata:
        parts.append("[Telegram context]\n" + json.dumps(metadata, ensure_ascii=False, indent=2))
    if files:
        file_lines = "\n".join(f"- {p} ({kind})" for p, kind in files)
        parts.append(f"[Files]\n{file_lines}")
    return "\n\n".join(parts)


@router.message()
async def on_message(message: types.Message) -> None:
    chat_id = message.chat.id
    if not _is_allowed(chat_id):
        return

    prompt = await _build_prompt(message)
    if not prompt:
        return

    async with _chat_lock(chat_id):
        renderer = build_renderer(settings.streaming_mode, telegram_ui, chat_id)

        if prompt.startswith("/"):
            command = prompt.split(maxsplit=1)[0]
            await renderer.on_tool("Command", {"command": command})

        try:
            await run_prompt(
                chat_id,
                prompt,
                claude_runner=agent_runner,
                session_store=session_store,
                ui=telegram_ui,
                deliver="final",
                start_typing=True,
                renderer=renderer,
            )
        except Exception:
            # run_prompt already logs; surface to the user so they aren't left hanging.
            await telegram_ui.send_text(chat_id, "Error processing your message.")


@router.callback_query(lambda cb: cb.data and cb.data.startswith(CANCEL_CALLBACK_PREFIX))
async def on_cancel(callback: types.CallbackQuery) -> None:
    chat_id = callback.message.chat.id if callback.message else 0
    if not _is_allowed(chat_id):
        await callback.answer()
        return

    cancelled = await agent_runner.cancel(chat_id)
    if cancelled:
        await callback.answer("Operation cancelled.")
        if callback.message:
            await telegram_ui.remove_reply_markup(chat_id, callback.message.message_id)
    else:
        await callback.answer()
        if callback.message:
            await telegram_ui.remove_reply_markup(chat_id, callback.message.message_id)
