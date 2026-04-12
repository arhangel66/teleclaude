import asyncio
import logging
import time

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096
THROTTLE_SECONDS = 2.0
TYPING_INTERVAL_SECONDS = 4.0

CANCEL_CALLBACK_PREFIX = "cancel:"


def _cancel_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data=f"{CANCEL_CALLBACK_PREFIX}{chat_id}")]
        ]
    )


class TelegramUI:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._typing_tasks: dict[int, asyncio.Task[None]] = {}

    async def start_typing(self, chat_id: int) -> None:
        """Start a background task that sends 'typing' action every 4 seconds."""
        await self.stop_typing(chat_id)

        async def _typing_loop() -> None:
            try:
                while True:
                    await self._bot.send_chat_action(chat_id=chat_id, action="typing")
                    await asyncio.sleep(TYPING_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("Typing action failed for chat_id=%d", chat_id)

        self._typing_tasks[chat_id] = asyncio.create_task(_typing_loop())

    async def stop_typing(self, chat_id: int) -> None:
        """Cancel the background typing task for the given chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def send_progress(self, chat_id: int, text: str) -> int:
        """Send initial progress message with cancel button, return message_id."""
        truncated = text[:MAX_MESSAGE_LENGTH]
        msg = await self._bot.send_message(
            chat_id, truncated, reply_markup=_cancel_keyboard(chat_id)
        )
        return msg.message_id

    async def update_progress(
        self, chat_id: int, message_id: int, text: str
    ) -> None:
        """Edit progress message with cancel button (caller handles throttling)."""
        truncated = text[:MAX_MESSAGE_LENGTH]
        try:
            await self._bot.edit_message_text(
                truncated, chat_id=chat_id, message_id=message_id,
                reply_markup=_cancel_keyboard(chat_id),
            )
        except Exception:
            pass  # Telegram may reject identical edits

    async def remove_reply_markup(self, chat_id: int, message_id: int) -> None:
        """Remove inline keyboard from a message."""
        try:
            await self._bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except Exception:
            pass

    async def send_final(
        self, chat_id: int, text: str, context_tokens: int
    ) -> None:
        """Send final response as new message(s) with context size footer."""
        if context_tokens > 0:
            full_text = f"{text}\n\n· {_format_tokens(context_tokens)}"
        else:
            full_text = text
        await self._send_long(chat_id, full_text)

    async def send_text(self, chat_id: int, text: str) -> None:
        """Send a simple text message."""
        await self._send_long(chat_id, text)

    async def _send_long(self, chat_id: int, text: str) -> None:
        """Split and send text that may exceed Telegram limit."""
        chunks = _split_text(text, MAX_MESSAGE_LENGTH)
        for chunk in chunks:
            await self._bot.send_message(chat_id, chunk)


class ProgressTracker:
    """Tracks progress state and handles throttled edits."""

    def __init__(self, ui: TelegramUI, chat_id: int) -> None:
        self._ui = ui
        self._chat_id = chat_id
        self._message_id: int | None = None
        self._last_edit: float = 0.0
        self._pending_text: str | None = None
        self._lines: list[str] = []

    async def on_text(self, text: str) -> None:
        self._lines = [text]
        await self._flush()

    async def on_tool_use(self, tool_name: str) -> None:
        self._lines.append(f"⚙ {tool_name}...")
        await self._flush()

    async def finish(self) -> None:
        """Flush any remaining pending edit."""
        if self._pending_text and self._message_id:
            await self._ui.update_progress(
                self._chat_id, self._message_id, self._pending_text
            )
            self._pending_text = None

    async def remove_cancel_button(self) -> None:
        """Remove the cancel inline keyboard from progress message."""
        if self._message_id:
            await self._ui.remove_reply_markup(self._chat_id, self._message_id)

    async def delete_progress(self) -> None:
        """Delete the progress message after final is sent."""
        if self._message_id:
            try:
                await self._ui._bot.delete_message(
                    self._chat_id, self._message_id
                )
            except Exception:
                pass

    async def _flush(self) -> None:
        text = "\n".join(self._lines)

        if self._message_id is None:
            self._message_id = await self._ui.send_progress(
                self._chat_id, text
            )
            self._last_edit = time.monotonic()
            return

        now = time.monotonic()
        if now - self._last_edit >= THROTTLE_SECONDS:
            await self._ui.update_progress(
                self._chat_id, self._message_id, text
            )
            self._last_edit = now
            self._pending_text = None
        else:
            self._pending_text = text


def _format_tokens(tokens: int) -> str:
    if tokens >= 1000:
        return f"{tokens // 1000}k"
    return str(tokens)


def _split_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Try to split at newline
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
