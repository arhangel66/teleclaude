from src.bot.services.claude_runner import (
    ClaudeRunner,
    TextEvent,
    ThinkingEvent,
    ToolUseEvent,
)


def _runner() -> ClaudeRunner:
    return ClaudeRunner(claude_binary="claude", working_directory="/tmp")


def test_parse_thinking_block_emits_thinking_event() -> None:
    # Arrange
    data = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "thinking", "thinking": "Let me think about this..."},
                {"type": "text", "text": "The answer is 4."},
            ],
            "usage": {},
        },
    }

    # Act
    events = _runner()._parse_event(data)

    # Assert
    kinds = [type(e).__name__ for e in events]
    assert "ThinkingEvent" in kinds
    assert "TextEvent" in kinds
    thinking = next(e for e in events if isinstance(e, ThinkingEvent))
    assert thinking.text == "Let me think about this..."


def test_parse_mixed_blocks_preserves_order() -> None:
    # Arrange
    data = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "thinking", "thinking": "hm"},
                {"type": "tool_use", "name": "Read"},
                {"type": "text", "text": "done"},
            ],
            "usage": {},
        },
    }

    # Act
    events = _runner()._parse_event(data)

    # Assert
    assert [type(e).__name__ for e in events] == [
        "ThinkingEvent",
        "ToolUseEvent",
        "TextEvent",
    ]
    assert isinstance(events[1], ToolUseEvent)
    assert events[1].tool_name == "Read"
    assert events[1].tool_input == {}
    assert isinstance(events[2], TextEvent)
    assert events[2].text == "done"


def test_parse_tool_use_carries_input() -> None:
    # Arrange
    data = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Read",
                    "input": {"file_path": "/tmp/x.py"},
                }
            ],
            "usage": {},
        },
    }

    # Act
    events = _runner()._parse_event(data)

    # Assert
    tool = next(e for e in events if isinstance(e, ToolUseEvent))
    assert tool.tool_name == "Read"
    assert tool.tool_input == {"file_path": "/tmp/x.py"}


def test_parse_empty_thinking_is_skipped() -> None:
    # Arrange
    data = {
        "type": "assistant",
        "message": {
            "content": [{"type": "thinking", "thinking": ""}],
            "usage": {},
        },
    }

    # Act
    events = _runner()._parse_event(data)

    # Assert
    assert not any(isinstance(e, ThinkingEvent) for e in events)


def test_parse_thinking_fallback_to_text_field() -> None:
    # Arrange: some Claude CLI variants store thinking in 'text' instead of 'thinking'
    data = {
        "type": "assistant",
        "message": {
            "content": [{"type": "thinking", "text": "reasoning here"}],
            "usage": {},
        },
    }

    # Act
    events = _runner()._parse_event(data)

    # Assert
    thinking = [e for e in events if isinstance(e, ThinkingEvent)]
    assert len(thinking) == 1
    assert thinking[0].text == "reasoning here"
