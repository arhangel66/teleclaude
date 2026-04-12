import logging
import time
from pathlib import Path

from aiogram import Router, types
from aiogram.filters import Command

from src.bot.construct import bot, claude_runner, session_store, settings, telegram_ui
from src.bot.services.claude_runner import ResultEvent, SystemEvent, TextEvent, ToolUseEvent
from src.bot.services.telegram_ui import CANCEL_CALLBACK_PREFIX, ProgressTracker

logger = logging.getLogger(__name__)
router = Router()

FILES_DIR = Path("files")


async def _download_file(message: types.Message) -> tuple[Path, str] | None:
    """Download attachment from message. Returns (path, caption) or None."""
    chat_id = message.chat.id
    ts = int(time.time())
    dest_dir = FILES_DIR / str(chat_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    file_id: str | None = None
    filename: str | None = None

    if message.photo:
        largest = message.photo[-1]
        file_id = largest.file_id
        filename = f"{ts}_{largest.file_id}.jpg"
    elif message.voice:
        file_id = message.voice.file_id
        filename = f"{ts}_voice.ogg"
    elif message.video:
        file_id = message.video.file_id
        filename = f"{ts}_video.mp4"
    elif message.document:
        file_id = message.document.file_id
        original_name = message.document.file_name or "document"
        filename = f"{ts}_{original_name}"

    if not file_id or not filename:
        return None

    dest_path = dest_dir / filename
    await bot.download(file_id, destination=dest_path)
    caption = message.caption or ""
    return dest_path.resolve(), caption


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


@router.message()
async def on_message(message: types.Message) -> None:
    chat_id = message.chat.id
    if not _is_allowed(chat_id):
        return

    # Build prompt from text or file
    prompt: str | None = None
    file_result = await _download_file(message)
    if file_result:
        file_path, caption = file_result
        if caption:
            prompt = f"User sent a file: {file_path}\n\n{caption}"
        else:
            prompt = f"User sent a file: {file_path}"
    elif message.text:
        prompt = message.text

    if not prompt:
        return

    if claude_runner.is_busy(chat_id):
        await message.answer("Claude is still processing your previous message.")
        return

    session_id = await session_store.get(chat_id)
    progress = ProgressTracker(telegram_ui, chat_id)

    await telegram_ui.start_typing(chat_id)
    try:
        async for event in claude_runner.run(prompt, chat_id, session_id):
            if isinstance(event, SystemEvent):
                await session_store.set(chat_id, event.session_id)
            elif isinstance(event, TextEvent):
                await progress.on_text(event.text)
            elif isinstance(event, ToolUseEvent):
                await progress.on_tool_use(event.tool_name)
            elif isinstance(event, ResultEvent):
                logger.info("Got result, sending final (%d tokens)", event.context_tokens)
                await progress.finish()
                await progress.remove_cancel_button()
                await progress.delete_progress()
                await telegram_ui.send_final(chat_id, event.text, event.context_tokens)
                logger.info("Final message sent")
    except Exception:
        logger.exception("Error processing message for chat_id=%d", chat_id)
        await progress.remove_cancel_button()
        await telegram_ui.send_text(chat_id, "Error processing your message.")
    finally:
        await telegram_ui.stop_typing(chat_id)


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
