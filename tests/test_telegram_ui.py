from unittest.mock import MagicMock

import pytest

from src.bot.config import Settings
from src.bot.services.telegram_ui import (
    MAX_MESSAGE_LENGTH,
    TelegramUI,
    ThreadRenderer,
    _escape_md_v2,
    build_renderer,
)


class _Bot:
    def __init__(self) -> None:
        self.sends: list[tuple[int, str, str | None]] = []
        self.edits: list[tuple[int, int, str, str | None]] = []
        self.edit_markup_calls = 0
        self.delete_calls = 0
        self._next_id = 100
        self.edit_fail_count = 0

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self.sends.append((chat_id, text, parse_mode))
        self._next_id += 1
        msg = MagicMock()
        msg.message_id = self._next_id
        return msg

    async def edit_message_text(
        self, text, chat_id, message_id, reply_markup=None, parse_mode=None
    ):
        if self.edit_fail_count > 0:
            self.edit_fail_count -= 1
            raise RuntimeError("simulated edit failure")
        self.edits.append((chat_id, message_id, text, parse_mode))

    async def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
        self.edit_markup_calls += 1

    async def delete_message(self, chat_id, message_id):
        self.delete_calls += 1

    async def send_chat_action(self, chat_id, action):
        return None


@pytest.fixture
def ui_bot() -> tuple[TelegramUI, _Bot]:
    bot = _Bot()
    return TelegramUI(bot=bot), bot  # type: ignore[arg-type]


def _settings_env(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    monkeypatch.setenv("WORKING_DIRECTORY", "/tmp")
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")


def test_escape_md_v2_escapes_each_reserved_char_once() -> None:
    # Arrange
    reserved = "_*[]()~`>#+-=|{}.!\\"

    # Act / Assert
    for ch in reserved:
        assert _escape_md_v2(ch) == "\\" + ch


def test_escape_md_v2_leaves_plain_text_alone() -> None:
    # Arrange / Act / Assert
    assert _escape_md_v2("hello world 123") == "hello world 123"


def test_escape_md_v2_escapes_mixed_content() -> None:
    # Arrange / Act / Assert
    assert _escape_md_v2("a.b") == "a\\.b"
    assert _escape_md_v2("foo(bar)") == "foo\\(bar\\)"


@pytest.mark.asyncio
async def test_thread_renderer_appends_and_edits_in_place(ui_bot) -> None:
    # Arrange
    ui, bot = ui_bot
    renderer = ThreadRenderer(ui, chat_id=42)

    # Act
    await renderer.on_thinking("thinking now")
    await renderer.on_tool("Read", {"file_path": "/a.py"})
    await renderer.on_text("intermediate")
    await renderer.finish()

    # Assert — exactly one initial send_message, at least one MarkdownV2 edit
    assert len(bot.sends) == 1
    assert any(e[3] == "MarkdownV2" for e in bot.edits)


@pytest.mark.asyncio
async def test_thread_renderer_on_final_sends_new_message(ui_bot) -> None:
    # Arrange
    ui, bot = ui_bot
    renderer = ThreadRenderer(ui, chat_id=42)

    # Act
    await renderer.on_text("step 1")
    await renderer.on_final("final answer", 1500)

    # Assert — 2 send_messages; final text present; cancel markup removed
    assert len(bot.sends) == 2
    final_text = bot.sends[-1][1]
    assert "final answer" in final_text
    assert "1k" in final_text
    assert bot.edit_markup_calls >= 1


@pytest.mark.asyncio
async def test_thread_renderer_tail_trims_long_log(ui_bot) -> None:
    # Arrange
    ui, bot = ui_bot
    renderer = ThreadRenderer(ui, chat_id=42)
    for i in range(200):
        renderer._lines.append(_escape_md_v2(f"line {i} " + "x" * 100))

    # Act
    await renderer._flush(force=True)

    # Assert — single log message, within limit, contains truncation marker
    assert len(bot.sends) == 1
    body = bot.sends[0][1]
    assert len(body) <= MAX_MESSAGE_LENGTH
    assert "…" in body


@pytest.mark.asyncio
async def test_thread_renderer_wraps_expandable_over_threshold(ui_bot) -> None:
    # Arrange
    ui, bot = ui_bot
    renderer = ThreadRenderer(ui, chat_id=42)

    # Act — 5 lines > threshold (4)
    for i in range(5):
        await renderer.on_thinking(f"step {i}")
    await renderer.finish()

    # Assert — at least one rendered body uses expandable-blockquote markers
    bodies = [bot.sends[0][1]] + [e[2] for e in bot.edits]
    assert any(b.startswith("**>") and b.endswith("||") for b in bodies)


@pytest.mark.asyncio
async def test_thread_renderer_retries_plain_on_markdownv2_failure(ui_bot) -> None:
    # Arrange
    ui, bot = ui_bot
    renderer = ThreadRenderer(ui, chat_id=42)
    await renderer.on_text("first")  # creates log message
    bot.edit_fail_count = 1  # next MarkdownV2 edit will raise

    # Act
    await renderer.on_text("second")
    await renderer.finish()

    # Assert — no crash, and at least one edit was executed with parse_mode=None (plain retry)
    parse_modes = [e[3] for e in bot.edits]
    assert None in parse_modes


@pytest.mark.asyncio
async def test_thread_renderer_at_most_two_messages_end_to_end(ui_bot) -> None:
    # Arrange
    ui, bot = ui_bot
    renderer = ThreadRenderer(ui, chat_id=42)

    # Act
    await renderer.on_thinking("pondering")
    await renderer.on_tool("Grep", {"pattern": "foo"})
    await renderer.on_text("intermediate text")
    await renderer.on_final("done", 0)

    # Assert — exactly one log message + one final message
    assert len(bot.sends) == 2


def test_settings_default_streaming_mode_is_thread(monkeypatch) -> None:
    # Arrange
    _settings_env(monkeypatch)

    # Act
    settings = Settings(_env_file=None)

    # Assert
    assert settings.streaming_mode == "thread"


def test_settings_accepts_legacy_streaming_modes(monkeypatch) -> None:
    # Arrange
    _settings_env(monkeypatch)

    # Act / Assert
    for mode in ("verbose", "compact", "quiet", "thread"):
        monkeypatch.setenv("STREAMING_MODE", mode)
        settings = Settings(_env_file=None)
        assert settings.streaming_mode == mode


def test_build_renderer_thread_returns_thread_renderer() -> None:
    # Arrange
    ui = MagicMock()

    # Act / Assert
    assert isinstance(build_renderer("thread", ui, 1), ThreadRenderer)
