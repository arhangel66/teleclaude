from unittest.mock import MagicMock

import pytest

from src.bot.services.telegram_ui import (
    CompactRenderer,
    QuietRenderer,
    TelegramUI,
    VerboseRenderer,
    _format_tool_detail,
    _format_tool_line,
    build_renderer,
)


class _CountingBot:
    """Minimal async Bot stub that counts send_message calls."""

    def __init__(self) -> None:
        self.send_calls = 0
        self.edit_calls = 0
        self.edit_markup_calls = 0
        self.delete_calls = 0
        self._next_id = 100

    async def send_message(self, chat_id, text, reply_markup=None):
        self.send_calls += 1
        self._next_id += 1
        msg = MagicMock()
        msg.message_id = self._next_id
        return msg

    async def edit_message_text(self, text, chat_id, message_id, reply_markup=None):
        self.edit_calls += 1

    async def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
        self.edit_markup_calls += 1

    async def delete_message(self, chat_id, message_id):
        self.delete_calls += 1

    async def send_chat_action(self, chat_id, action):
        return None


@pytest.fixture
def counting_ui() -> tuple[TelegramUI, _CountingBot]:
    bot = _CountingBot()
    return TelegramUI(bot=bot), bot  # type: ignore[arg-type]


async def _drive(renderer, events: list[tuple[str, str]]) -> None:
    for kind, payload in events:
        if kind == "text":
            await renderer.on_text(payload)
        elif kind == "tool":
            await renderer.on_tool(payload)
        elif kind == "thinking":
            await renderer.on_thinking(payload)
    await renderer.finish()


@pytest.mark.asyncio
async def test_verbose_sends_one_message_per_event(
    counting_ui: tuple[TelegramUI, _CountingBot],
) -> None:
    # Arrange
    ui, bot = counting_ui
    renderer = VerboseRenderer(ui, chat_id=42)
    events = [
        ("thinking", "pondering"),
        ("text", "hello"),
        ("tool", "Read"),
        ("text", "world"),
    ]

    # Act
    await _drive(renderer, events)

    # Assert — one send per non-empty event (4), plus cancel-markup removals (3 + 1 finish)
    assert bot.send_calls == 4
    assert bot.edit_markup_calls >= 1  # at least final cancel removal


@pytest.mark.asyncio
async def test_verbose_skips_empty_text_and_thinking(
    counting_ui: tuple[TelegramUI, _CountingBot],
) -> None:
    # Arrange
    ui, bot = counting_ui
    renderer = VerboseRenderer(ui, chat_id=42)

    # Act
    await renderer.on_text("")
    await renderer.on_thinking("   ")
    await renderer.on_tool("Bash")
    await renderer.finish()

    # Assert — only tool message sent
    assert bot.send_calls == 1


@pytest.mark.asyncio
async def test_compact_uses_single_message_edits(
    counting_ui: tuple[TelegramUI, _CountingBot],
) -> None:
    # Arrange
    ui, bot = counting_ui
    renderer = CompactRenderer(ui, chat_id=42)
    events = [
        ("text", "hello"),
        ("tool", "Read"),
        ("text", "world"),
    ]

    # Act
    await _drive(renderer, events)

    # Assert — exactly one send_message (initial progress), subsequent events edit
    assert bot.send_calls == 1
    assert bot.delete_calls == 0  # finish() no longer deletes; on_final does


@pytest.mark.asyncio
async def test_quiet_sends_nothing_during_stream(
    counting_ui: tuple[TelegramUI, _CountingBot],
) -> None:
    # Arrange
    ui, bot = counting_ui
    renderer = QuietRenderer(ui, chat_id=42)
    events = [
        ("text", "hello"),
        ("tool", "Read"),
        ("thinking", "hmm"),
        ("text", "done"),
    ]

    # Act
    await _drive(renderer, events)

    # Assert
    assert bot.send_calls == 0


@pytest.mark.asyncio
async def test_quiet_on_final_sends_message(
    counting_ui: tuple[TelegramUI, _CountingBot],
) -> None:
    # Arrange
    ui, bot = counting_ui
    renderer = QuietRenderer(ui, chat_id=42)

    # Act
    await renderer.on_final("hello", 0)

    # Assert
    assert bot.send_calls == 1


@pytest.mark.asyncio
async def test_verbose_on_final_dedupes_when_last_is_same_text(
    counting_ui: tuple[TelegramUI, _CountingBot],
) -> None:
    # Arrange
    ui, bot = counting_ui
    renderer = VerboseRenderer(ui, chat_id=42)

    # Act
    await renderer.on_text("done")
    send_calls_before = bot.send_calls
    await renderer.on_final("done", 2500)

    # Assert — no new message, just edit-in-place
    assert bot.send_calls == send_calls_before
    assert bot.edit_calls >= 1


@pytest.mark.asyncio
async def test_verbose_on_final_sends_new_when_last_is_not_text(
    counting_ui: tuple[TelegramUI, _CountingBot],
) -> None:
    # Arrange
    ui, bot = counting_ui
    renderer = VerboseRenderer(ui, chat_id=42)

    # Act
    await renderer.on_tool("Read", {"file_path": "/a.py"})
    send_calls_before = bot.send_calls
    await renderer.on_final("hello", 100)

    # Assert — new final message sent
    assert bot.send_calls == send_calls_before + 1


@pytest.mark.asyncio
async def test_verbose_on_final_sends_new_when_text_differs(
    counting_ui: tuple[TelegramUI, _CountingBot],
) -> None:
    # Arrange
    ui, bot = counting_ui
    renderer = VerboseRenderer(ui, chat_id=42)

    # Act
    await renderer.on_text("streaming text")
    send_calls_before = bot.send_calls
    await renderer.on_final("final text", 100)

    # Assert — final text differs, must send new message
    assert bot.send_calls == send_calls_before + 1


@pytest.mark.asyncio
async def test_compact_on_final_deletes_progress_and_sends(
    counting_ui: tuple[TelegramUI, _CountingBot],
) -> None:
    # Arrange
    ui, bot = counting_ui
    renderer = CompactRenderer(ui, chat_id=42)

    # Act
    await renderer.on_text("streaming")
    await renderer.on_final("final result", 500)

    # Assert — 1 progress send + 1 final send, progress deleted
    assert bot.send_calls == 2
    assert bot.delete_calls == 1


@pytest.mark.asyncio
async def test_build_renderer_maps_modes() -> None:
    # Arrange
    ui = MagicMock()

    # Act / Assert
    assert isinstance(build_renderer("verbose", ui, 1), VerboseRenderer)
    assert isinstance(build_renderer("compact", ui, 1), CompactRenderer)
    assert isinstance(build_renderer("quiet", ui, 1), QuietRenderer)


def test_format_tool_detail_picks_known_key() -> None:
    # Arrange / Act / Assert
    assert _format_tool_detail("Read", {"file_path": "/a/b.py"}) == "/a/b.py"
    assert _format_tool_detail("Bash", {"description": "run tests", "command": "pytest"}) == "run tests"
    assert _format_tool_detail("Bash", {"command": "pytest -v"}) == "pytest -v"
    assert _format_tool_detail("Grep", {"pattern": "foo"}) == "foo"
    assert _format_tool_detail("Unknown", {"path": "/x"}) == "/x"


def test_format_tool_detail_truncates_long_values() -> None:
    # Arrange
    long = "a" * 200

    # Act
    detail = _format_tool_detail("Bash", {"command": long})

    # Assert
    assert detail.endswith("…")
    assert len(detail) <= 100


def test_format_tool_detail_handles_missing_input() -> None:
    # Arrange / Act / Assert
    assert _format_tool_detail("Read", None) == ""
    assert _format_tool_detail("Read", {}) == ""


def test_format_tool_line_includes_detail() -> None:
    # Arrange / Act / Assert
    assert _format_tool_line("Read", {"file_path": "/a.py"}) == "⚙ Read: /a.py"
    assert _format_tool_line("Read", None) == "⚙ Read"
    assert _format_tool_line("Read", {"file_path": "/a.py"}, suffix="...") == "⚙ Read: /a.py..."


def test_build_renderer_rejects_unknown_mode() -> None:
    # Arrange
    ui = MagicMock()

    # Act / Assert
    with pytest.raises(ValueError):
        build_renderer("loud", ui, 1)


@pytest.mark.asyncio
async def test_verbose_cancel_button_migrates(
    counting_ui: tuple[TelegramUI, _CountingBot],
) -> None:
    # Arrange
    ui, bot = counting_ui
    renderer = VerboseRenderer(ui, chat_id=42)

    # Act
    await renderer.on_text("first")
    first_edit_markup = bot.edit_markup_calls
    await renderer.on_text("second")

    # Assert — second emit triggers one reply-markup removal (button migration)
    assert bot.edit_markup_calls == first_edit_markup + 1
