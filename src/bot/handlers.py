import logging
import time
from pathlib import Path

from aiogram import Router, types
from aiogram.filters import Command

from src.bot.construct import (
    bot,
    claude_runner,
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

AttachmentResult = tuple[Path, str, str]  # (path, caption, kind)


async def _download_file(message: types.Message) -> AttachmentResult | None:
    """Download attachment from message. Returns (path, caption, kind) or None.

    kind ∈ {"photo", "voice", "video", "video_note", "document"}.
    """
    chat_id = message.chat.id
    ts = int(time.time())
    dest_dir = FILES_DIR / str(chat_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    file_id: str | None = None
    filename: str | None = None
    kind: str | None = None

    if message.photo:
        largest = message.photo[-1]
        file_id = largest.file_id
        filename = f"{ts}_{largest.file_id}.jpg"
        kind = "photo"
    elif message.voice:
        file_id = message.voice.file_id
        filename = f"{ts}_voice.ogg"
        kind = "voice"
    elif getattr(message, "video_note", None):
        file_id = message.video_note.file_id
        filename = f"{ts}_video_note.mp4"
        kind = "video_note"
    elif message.video:
        file_id = message.video.file_id
        filename = f"{ts}_video.mp4"
        kind = "video"
    elif message.document:
        file_id = message.document.file_id
        original_name = message.document.file_name or "document"
        filename = f"{ts}_{original_name}"
        kind = "document"

    if not file_id or not filename or not kind:
        return None

    dest_path = dest_dir / filename
    await bot.download(file_id, destination=dest_path)
    caption = message.caption or ""
    return dest_path.resolve(), caption, kind


def _is_allowed(chat_id: int) -> bool:
    return chat_id in settings.allowed_chat_ids


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    if not _is_allowed(message.chat.id):
        return
    await message.answer("Claude Code bridge is ready. Send me a message.")


@router.message(Command("new"))
async def cmd_new(message: types.Message) -> None:
    if not _is_allowed(message.chat.id):
        return
    await session_store.reset(message.chat.id)
    await message.answer("New session started.")


async def _build_prompt(message: types.Message) -> str | None:
    """Resolve the message into a Claude prompt. Returns None if unusable."""
    file_result = await _download_file(message)
    if file_result:
        file_path, caption, kind = file_result
        if kind in ("voice", "video_note"):
            try:
                transcript = await transcriber.transcribe(file_path)
            except TranscriptionError as exc:
                logger.warning("Transcription failed for chat_id=%d: %s", message.chat.id, exc)
                await telegram_ui.send_text(
                    message.chat.id, f"Не удалось распознать речь: {exc}"
                )
                return None
            logger.info("Transcribed voice (%d chars)", len(transcript))
            prompt = f"(voice transcript): {transcript}"
            if caption:
                prompt = f"{prompt}\n\n{caption}"
            return prompt
        if caption:
            return f"User sent a file: {file_path}\n\n{caption}"
        return f"User sent a file: {file_path}"
    if message.text:
        return message.text
    return None


@router.message()
async def on_message(message: types.Message) -> None:
    chat_id = message.chat.id
    if not _is_allowed(chat_id):
        return

    prompt = await _build_prompt(message)
    if not prompt:
        return

    if claude_runner.is_busy(chat_id):
        await message.answer("Claude is still processing your previous message.")
        return

    renderer = build_renderer(settings.streaming_mode, telegram_ui, chat_id)

    try:
        await run_prompt(
            chat_id,
            prompt,
            claude_runner=claude_runner,
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

    cancelled = await claude_runner.cancel(chat_id)
    if cancelled:
        await callback.answer("Operation cancelled.")
        if callback.message:
            await telegram_ui.remove_reply_markup(chat_id, callback.message.message_id)
    else:
        await callback.answer()
        if callback.message:
            await telegram_ui.remove_reply_markup(chat_id, callback.message.message_id)
