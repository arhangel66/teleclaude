from unittest.mock import MagicMock

import pytest

from src.bot.services.telegram_ui import (
    CompactRenderer,
    QuietRenderer,
    TelegramUI,
    VerboseRenderer,
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
    assert bot.delete_calls == 1  # progress message deleted on finish


@pytest.mark.asyncio
async def test_quiet_sends_nothing_during_stream(
    counting_ui: tuple[TelegramUI, _CountingBot],
) -> None:
    # Arrange
    ui, bot = counting_ui
    renderer = QuietRenderer()
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
async def test_build_renderer_maps_modes() -> None:
    # Arrange
    ui = MagicMock()

    # Act / Assert
    assert isinstance(build_renderer("verbose", ui, 1), VerboseRenderer)
    assert isinstance(build_renderer("compact", ui, 1), CompactRenderer)
    assert isinstance(build_renderer("quiet", ui, 1), QuietRenderer)


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
