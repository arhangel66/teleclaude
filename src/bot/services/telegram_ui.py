import asyncio
import logging
import re
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

EXPANDABLE_THRESHOLD = 4
TRUNCATION_MARKER = "…"
_MD_V2_RESERVED = set(r"_*[]()~`>#+-=|{}.!\\")


def _escape_html(text: str) -> str:
    """Escape Telegram HTML reserved characters (&, <, >)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_MD_CODE_BLOCK = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
_MD_CODE_INLINE = re.compile(r"`([^`\n]+)`")
_MD_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_MD_BOLD_ALT = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _markdown_to_html(text: str) -> str:
    """Convert a safe subset of Markdown to Telegram HTML.

    Supports: **bold**, *bold*, `code`, ```code blocks```, [text](url).
    Everything else is HTML-escaped.
    """
    placeholders: list[str] = []

    def _stash(html: str) -> str:
        placeholders.append(html)
        return f"\x00{len(placeholders) - 1}\x00"

    def _stash_block(m: "re.Match[str]") -> str:
        return _stash(f"<pre>{_escape_html(m.group(2))}</pre>")

    def _stash_inline(m: "re.Match[str]") -> str:
        return _stash(f"<code>{_escape_html(m.group(1))}</code>")

    def _stash_link(m: "re.Match[str]") -> str:
        return _stash(f'<a href="{_escape_html(m.group(2))}">{_escape_html(m.group(1))}</a>')

    text = _MD_CODE_BLOCK.sub(_stash_block, text)
    text = _MD_CODE_INLINE.sub(_stash_inline, text)
    text = _MD_LINK.sub(_stash_link, text)

    text = _escape_html(text)
    text = _MD_BOLD.sub(r"<b>\1</b>", text)
    text = _MD_BOLD_ALT.sub(r"<b>\1</b>", text)

    for i, html in enumerate(placeholders):
        text = text.replace(f"\x00{i}\x00", html)
    return text


def _render_block_html(lines: list[str]) -> str:
    """Render raw log lines as an HTML blockquote (tail-trims if oversize)."""
    work = list(lines)
    truncated = False
    while True:
        all_lines = ([TRUNCATION_MARKER] if truncated else []) + work
        inner = "\n".join(_escape_html(ln) for ln in all_lines)
        tag = (
            "<blockquote expandable>"
            if len(all_lines) > EXPANDABLE_THRESHOLD
            else "<blockquote>"
        )
        body = f"{tag}{inner}</blockquote>"
        if len(body) <= MAX_MESSAGE_LENGTH:
            return body
        if len(work) <= 1:
            return body[:MAX_MESSAGE_LENGTH]
        work = work[1:]
        truncated = True


def _escape_md_v2(text: str) -> str:
    """Escape Telegram MarkdownV2 reserved characters."""
    return "".join("\\" + ch if ch in _MD_V2_RESERVED else ch for ch in text)


def _strip_md_v2_escapes(text: str) -> str:
    """Remove MarkdownV2 escape backslashes for plain-text fallback."""
    result: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] in _MD_V2_RESERVED:
            result.append(text[i + 1])
            i += 2
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def _assemble_blockquote(lines: list[str], truncated: bool) -> str:
    all_lines = ([TRUNCATION_MARKER] if truncated else []) + list(lines)
    if not all_lines:
        return ""
    if len(all_lines) > EXPANDABLE_THRESHOLD:
        rendered = ["**> " + all_lines[0]]
        for ln in all_lines[1:-1]:
            rendered.append("> " + ln)
        rendered.append("> " + all_lines[-1] + "||")
        return "\n".join(rendered)
    return "\n".join("> " + ln for ln in all_lines)


def _assemble_plain(lines: list[str], truncated: bool) -> str:
    """Render log lines as plain text (no blockquote markup)."""
    all_lines = ([TRUNCATION_MARKER] if truncated else []) + list(lines)
    return "\n".join(all_lines)


def _render_block(lines: list[str]) -> str:
    """Render raw log lines as a MarkdownV2 blockquote (tail-trims if oversize)."""
    work = list(lines)
    truncated = False
    while True:
        body = _assemble_blockquote([_escape_md_v2(ln) for ln in work], truncated)
        if len(body) <= MAX_MESSAGE_LENGTH:
            return body
        if len(work) <= 1:
            return body[:MAX_MESSAGE_LENGTH]
        work = work[1:]
        truncated = True


def _render_block_plain(lines: list[str]) -> str:
    """Render raw log lines as plain text (for fallback when MarkdownV2 fails)."""
    work = list(lines)
    truncated = False
    while True:
        body = _assemble_plain(work, truncated)
        if len(body) <= MAX_MESSAGE_LENGTH:
            return body
        if len(work) <= 1:
            return body[:MAX_MESSAGE_LENGTH]
        work = work[1:]
        truncated = True

MAX_TOOL_DETAIL_LEN = 100

_TOOL_DETAIL_KEYS: dict[str, tuple[str, ...]] = {
    "Read": ("file_path",),
    "Edit": ("file_path",),
    "Write": ("file_path",),
    "NotebookEdit": ("notebook_path", "file_path"),
    "Bash": ("description", "command"),
    "Grep": ("pattern",),
    "Glob": ("pattern",),
    "Task": ("description",),
    "WebFetch": ("url",),
    "WebSearch": ("query",),
    "Skill": ("skill", "name"),
    "SlashCommand": ("command", "name"),
    "TodoWrite": (),
}

_DEFAULT_DETAIL_KEYS = (
    "file_path", "path", "pattern", "query", "description", "command", "url",
)


def _format_tool_detail(tool_name: str, tool_input: dict | None) -> str:
    """Pick a short, human-readable detail from a tool's input payload."""
    if not tool_input:
        return ""
    keys = _TOOL_DETAIL_KEYS.get(tool_name, _DEFAULT_DETAIL_KEYS)
    for key in keys:
        value = tool_input.get(key)
        if value:
            text = str(value).replace("\n", " ").strip()
            if len(text) > MAX_TOOL_DETAIL_LEN:
                text = text[: MAX_TOOL_DETAIL_LEN - 1] + "…"
            return text
    return ""


def _format_tool_line(tool_name: str, tool_input: dict | None, *, suffix: str = "") -> str:
    detail = _format_tool_detail(tool_name, tool_input)
    body = f"{tool_name}: {detail}" if detail else tool_name
    return f"{TOOL_PREFIX}{body}{suffix}"


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

    async def send_progress(
        self, chat_id: int, text: str, *, parse_mode: str | None = None,
    ) -> int:
        """Send initial progress message with cancel button, return message_id."""
        truncated = text[:MAX_MESSAGE_LENGTH]
        kwargs: dict[str, str] = {}
        if parse_mode is not None:
            kwargs["parse_mode"] = parse_mode
        msg = await self._bot.send_message(
            chat_id, truncated, reply_markup=_cancel_keyboard(chat_id), **kwargs,
        )
        return msg.message_id

    async def update_progress(
        self, chat_id: int, message_id: int, text: str,
        *, parse_mode: str | None = None,
    ) -> bool:
        """Edit progress message with cancel button; returns True on success."""
        truncated = text[:MAX_MESSAGE_LENGTH]
        kwargs: dict[str, str] = {}
        if parse_mode is not None:
            kwargs["parse_mode"] = parse_mode
        try:
            await self._bot.edit_message_text(
                truncated, chat_id=chat_id, message_id=message_id,
                reply_markup=_cancel_keyboard(chat_id), **kwargs,
            )
            return True
        except Exception as exc:
            msg = str(exc).lower()
            # "message is not modified" — identical edit, not a real failure
            if "not modified" in msg:
                return True
            if parse_mode:
                logger.warning(
                    "edit_message_text failed (parse_mode=%s): %s | text[:200]=%r",
                    parse_mode, exc, truncated[:200],
                )
            return False

    async def update_progress_md(
        self, chat_id: int, message_id: int, text: str,
    ) -> None:
        """Edit with MarkdownV2, falling back to plain text on failure."""
        ok = await self.update_progress(
            chat_id, message_id, text, parse_mode="MarkdownV2",
        )
        if not ok:
            logger.debug("MarkdownV2 edit failed for chat %d, retrying plain", chat_id)
            await self.update_progress(chat_id, message_id, _strip_md_v2_escapes(text))

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

    async def edit_plain(
        self, chat_id: int, message_id: int, text: str
    ) -> bool:
        """Edit an existing message, stripping any inline keyboard. Returns success."""
        truncated = text[:MAX_MESSAGE_LENGTH]
        try:
            await self._bot.edit_message_text(
                truncated, chat_id=chat_id, message_id=message_id, reply_markup=None,
            )
            return True
        except Exception:
            return False

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
        """Split and send text that may exceed Telegram limit.

        Converts a safe subset of Markdown to HTML for reliable rendering,
        falls back to plain text if Telegram rejects the markup.
        """
        chunks = _split_text(text, MAX_MESSAGE_LENGTH)
        for chunk in chunks:
            try:
                await self._bot.send_message(
                    chat_id, _markdown_to_html(chunk), parse_mode="HTML",
                )
            except Exception as exc:
                logger.warning(
                    "send_message HTML failed: %s | chunk[:200]=%r",
                    exc, chunk[:200],
                )
                await self._bot.send_message(chat_id, chunk)


class StreamRenderer:
    """Base interface for rendering claude event streams to Telegram."""

    async def on_text(self, text: str) -> None: ...
    async def on_tool(self, tool_name: str, tool_input: dict | None = None) -> None: ...
    async def on_thinking(self, text: str) -> None: ...
    async def on_final(self, text: str, context_tokens: int) -> None: ...
    async def finish(self) -> None: ...
    async def cleanup(self) -> None: ...


class VerboseRenderer(StreamRenderer):
    """Send each event as a separate Telegram message, cancel button migrates."""

    def __init__(self, ui: TelegramUI, chat_id: int) -> None:
        self._ui = ui
        self._chat_id = chat_id
        self._last_message_id: int | None = None
        self._last_text_message_id: int | None = None
        self._last_text: str | None = None

    async def _emit(self, text: str, *, is_text: bool = False) -> None:
        new_id = await self._ui.send_step(self._chat_id, text, with_cancel=True)
        if self._last_message_id is not None:
            await self._ui.remove_reply_markup(self._chat_id, self._last_message_id)
        self._last_message_id = new_id
        if is_text:
            self._last_text_message_id = new_id
            self._last_text = text
        else:
            self._last_text_message_id = None
            self._last_text = None

    async def on_text(self, text: str) -> None:
        if text.strip():
            await self._emit(text, is_text=True)

    async def on_tool(self, tool_name: str, tool_input: dict | None = None) -> None:
        await self._emit(_format_tool_line(tool_name, tool_input))

    async def on_thinking(self, text: str) -> None:
        if text.strip():
            await self._emit(f"{THINKING_PREFIX}{text}")

    async def on_final(self, text: str, context_tokens: int) -> None:
        """Dedupe: if last emitted was the same text, just append token footer in-place."""
        footer = f" ({_format_tokens(context_tokens)})" if context_tokens > 0 else ""
        combined = f"{text}{footer}"
        can_edit = (
            self._last_text_message_id is not None
            and self._last_text == text
            and len(combined) <= MAX_MESSAGE_LENGTH
        )
        if can_edit and await self._ui.edit_plain(
            self._chat_id, self._last_text_message_id, combined
        ):
            self._last_message_id = None
            return
        if self._last_message_id is not None:
            await self._ui.remove_reply_markup(self._chat_id, self._last_message_id)
            self._last_message_id = None
        await self._ui.send_final(self._chat_id, text, context_tokens)

    async def finish(self) -> None:
        if self._last_message_id is not None:
            await self._ui.remove_reply_markup(self._chat_id, self._last_message_id)

    async def cleanup(self) -> None:
        await self.finish()


class CompactRenderer(StreamRenderer):
    """Legacy single-message-with-edit UX via ProgressTracker."""

    def __init__(self, ui: TelegramUI, chat_id: int) -> None:
        self._ui = ui
        self._chat_id = chat_id
        self._tracker = ProgressTracker(ui, chat_id)

    async def on_text(self, text: str) -> None:
        await self._tracker.on_text(text)

    async def on_tool(self, tool_name: str, tool_input: dict | None = None) -> None:
        await self._tracker.on_tool_use(tool_name, tool_input)

    async def on_thinking(self, text: str) -> None:
        await self._tracker.on_thinking(text)

    async def on_final(self, text: str, context_tokens: int) -> None:
        await self._tracker.finish()
        await self._tracker.remove_cancel_button()
        await self._tracker.delete_progress()
        await self._ui.send_final(self._chat_id, text, context_tokens)

    async def finish(self) -> None:
        await self._tracker.finish()
        await self._tracker.remove_cancel_button()

    async def cleanup(self) -> None:
        await self._tracker.remove_cancel_button()


class QuietRenderer(StreamRenderer):
    """No step messages — only the final response is sent."""

    def __init__(self, ui: TelegramUI, chat_id: int) -> None:
        self._ui = ui
        self._chat_id = chat_id

    async def on_text(self, text: str) -> None:
        return None

    async def on_tool(self, tool_name: str, tool_input: dict | None = None) -> None:
        return None

    async def on_thinking(self, text: str) -> None:
        return None

    async def on_final(self, text: str, context_tokens: int) -> None:
        await self._ui.send_final(self._chat_id, text, context_tokens)

    async def finish(self) -> None:
        return None

    async def cleanup(self) -> None:
        return None


class ThreadRenderer(StreamRenderer):
    """Two-message UX: one edited-in-place MarkdownV2 blockquote log + one final-answer message."""

    def __init__(self, ui: TelegramUI, chat_id: int) -> None:
        self._ui = ui
        self._chat_id = chat_id
        self._lines: list[str] = []
        self._message_id: int | None = None
        self._last_edit: float = 0.0
        self._pending: bool = False

    async def on_text(self, text: str) -> None:
        # Text events include the final answer fragments — skip them
        # to avoid duplicating the answer in both the log and the final message.
        pass

    async def on_tool(self, tool_name: str, tool_input: dict | None = None) -> None:
        self._lines.append(_format_tool_line(tool_name, tool_input))
        await self._flush()

    async def on_thinking(self, text: str) -> None:
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        if first_line:
            self._lines.append(f"{THINKING_PREFIX}{first_line}")
            await self._flush()

    async def on_final(self, text: str, context_tokens: int) -> None:
        await self._flush(force=True)
        if self._message_id is not None:
            await self._ui.remove_reply_markup(self._chat_id, self._message_id)
        await self._ui.send_final(self._chat_id, text, context_tokens)

    async def finish(self) -> None:
        await self._flush(force=True)
        if self._message_id is not None:
            await self._ui.remove_reply_markup(self._chat_id, self._message_id)

    async def cleanup(self) -> None:
        if self._message_id is not None:
            await self._ui.remove_reply_markup(self._chat_id, self._message_id)

    async def _flush(self, *, force: bool = False) -> None:
        if not self._lines:
            return
        body_html = _render_block_html(self._lines)
        body_plain = _render_block_plain(self._lines)

        if self._message_id is None:
            try:
                self._message_id = await self._ui.send_progress(
                    self._chat_id, body_html, parse_mode="HTML",
                )
            except Exception as exc:
                logger.warning(
                    "HTML send_progress failed: %s | body[:200]=%r",
                    exc, body_html[:200],
                )
                self._message_id = await self._ui.send_progress(
                    self._chat_id, body_plain,
                )
            self._last_edit = time.monotonic()
            self._pending = False
            return

        now = time.monotonic()
        if force or now - self._last_edit >= THROTTLE_SECONDS:
            ok = await self._ui.update_progress(
                self._chat_id, self._message_id, body_html, parse_mode="HTML",
            )
            if not ok:
                await self._ui.update_progress(
                    self._chat_id, self._message_id, body_plain,
                )
            self._last_edit = now
            self._pending = False
        else:
            self._pending = True


def build_renderer(mode: str, ui: TelegramUI, chat_id: int) -> StreamRenderer:
    if mode == "verbose":
        return VerboseRenderer(ui, chat_id)
    if mode == "compact":
        return CompactRenderer(ui, chat_id)
    if mode == "quiet":
        return QuietRenderer(ui, chat_id)
    if mode == "thread":
        return ThreadRenderer(ui, chat_id)
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

    async def on_tool_use(self, tool_name: str, tool_input: dict | None = None) -> None:
        self._lines.append(_format_tool_line(tool_name, tool_input, suffix="..."))
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
