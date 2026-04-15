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

TOOL_PREFIX = "⚙ "
THINKING_PREFIX = "🧠 "


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

    async def send_step(
        self, chat_id: int, text: str, *, with_cancel: bool
    ) -> int:
        """Send a new step message (not edit). Returns message_id.

        Used by verbose streaming mode for per-event messages.
        """
        truncated = text[:MAX_MESSAGE_LENGTH] if text else "…"
        reply_markup = _cancel_keyboard(chat_id) if with_cancel else None
        msg = await self._bot.send_message(chat_id, truncated, reply_markup=reply_markup)
        return msg.message_id

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
            full_text = f"{text} ({_format_tokens(context_tokens)})"
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


class StreamRenderer:
    """Base interface for rendering claude event streams to Telegram."""

    async def on_text(self, text: str) -> None: ...
    async def on_tool(self, tool_name: str) -> None: ...
    async def on_thinking(self, text: str) -> None: ...
    async def finish(self) -> None: ...
    async def cleanup(self) -> None: ...


class VerboseRenderer(StreamRenderer):
    """Send each event as a separate Telegram message, cancel button migrates."""

    def __init__(self, ui: TelegramUI, chat_id: int) -> None:
        self._ui = ui
        self._chat_id = chat_id
        self._last_message_id: int | None = None

    async def _emit(self, text: str) -> None:
        new_id = await self._ui.send_step(self._chat_id, text, with_cancel=True)
        if self._last_message_id is not None:
            await self._ui.remove_reply_markup(self._chat_id, self._last_message_id)
        self._last_message_id = new_id

    async def on_text(self, text: str) -> None:
        if text.strip():
            await self._emit(text)

    async def on_tool(self, tool_name: str) -> None:
        await self._emit(f"{TOOL_PREFIX}{tool_name}")

    async def on_thinking(self, text: str) -> None:
        if text.strip():
            await self._emit(f"{THINKING_PREFIX}{text}")

    async def finish(self) -> None:
        if self._last_message_id is not None:
            await self._ui.remove_reply_markup(self._chat_id, self._last_message_id)

    async def cleanup(self) -> None:
        await self.finish()


class CompactRenderer(StreamRenderer):
    """Legacy single-message-with-edit UX via ProgressTracker."""

    def __init__(self, ui: TelegramUI, chat_id: int) -> None:
        self._tracker = ProgressTracker(ui, chat_id)

    async def on_text(self, text: str) -> None:
        await self._tracker.on_text(text)

    async def on_tool(self, tool_name: str) -> None:
        await self._tracker.on_tool_use(tool_name)

    async def on_thinking(self, text: str) -> None:
        await self._tracker.on_thinking(text)

    async def finish(self) -> None:
        await self._tracker.finish()
        await self._tracker.remove_cancel_button()
        await self._tracker.delete_progress()

    async def cleanup(self) -> None:
        await self._tracker.remove_cancel_button()


class QuietRenderer(StreamRenderer):
    """No step messages — only the final response is sent."""

    async def on_text(self, text: str) -> None:
        return None

    async def on_tool(self, tool_name: str) -> None:
        return None

    async def on_thinking(self, text: str) -> None:
        return None

    async def finish(self) -> None:
        return None

    async def cleanup(self) -> None:
        return None


def build_renderer(mode: str, ui: TelegramUI, chat_id: int) -> StreamRenderer:
    if mode == "verbose":
        return VerboseRenderer(ui, chat_id)
    if mode == "compact":
        return CompactRenderer(ui, chat_id)
    if mode == "quiet":
        return QuietRenderer()
    raise ValueError(f"unknown streaming mode: {mode}")


class ProgressTracker:
    """Tracks progress state and handles throttled edits (compact mode)."""

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
        self._lines.append(f"{TOOL_PREFIX}{tool_name}...")
        await self._flush()

    async def on_thinking(self, text: str) -> None:
        snippet = text.strip().splitlines()[0] if text.strip() else ""
        if snippet:
            self._lines.append(f"{THINKING_PREFIX}{snippet}")
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
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
