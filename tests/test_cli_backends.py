from src.bot.services.cli_backends import ClaudeCliBackend, CodexCliBackend
from src.bot.services.runner_events import (
    ResultEvent,
    SystemEvent,
    TextEvent,
    ThinkingEvent,
    ToolUseEvent,
)


def test_claude_backend_builds_fresh_command() -> None:
    # Arrange
    backend = ClaudeCliBackend(claude_binary="claude")

    # Act
    command = backend.build_command("hello", session_id=None)

    # Assert
    assert command == [
        "claude",
        "-p",
        "hello",
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
    ]


def test_claude_backend_builds_resume_command() -> None:
    # Arrange
    backend = ClaudeCliBackend(claude_binary="claude")

    # Act
    command = backend.build_command("hello", session_id="sess-1")

    # Assert
    assert command[-2:] == ["--resume", "sess-1"]


def test_claude_backend_normalizes_json_events() -> None:
    # Arrange
    parser = ClaudeCliBackend(claude_binary="claude").create_parser()

    # Act
    events = []
    events.extend(parser.parse({"type": "system", "session_id": "sess-1"}))
    events.extend(
        parser.parse(
            {
                "type": "assistant",
                "message": {
                    "usage": {"input_tokens": 10},
                    "content": [
                        {"type": "thinking", "thinking": "hm"},
                        {"type": "tool_use", "name": "Read", "input": {"file": "x"}},
                        {"type": "text", "text": "hello"},
                    ],
                },
            }
        )
    )
    events.extend(parser.parse({"type": "result", "result": "done", "usage": {}}))

    # Assert
    assert [type(event).__name__ for event in events] == [
        "SystemEvent",
        "ThinkingEvent",
        "ToolUseEvent",
        "TextEvent",
        "ResultEvent",
    ]
    assert isinstance(events[0], SystemEvent)
    assert events[0].session_id == "sess-1"
    assert isinstance(events[1], ThinkingEvent)
    assert events[1].text == "hm"
    assert isinstance(events[2], ToolUseEvent)
    assert events[2].tool_name == "Read"
    assert events[2].tool_input == {"file": "x"}
    assert isinstance(events[3], TextEvent)
    assert events[3].text == "hello"
    assert isinstance(events[4], ResultEvent)
    assert events[4].text == "done"
    assert events[4].context_tokens == 10


def test_codex_backend_builds_fresh_command() -> None:
    # Arrange
    backend = CodexCliBackend(codex_binary="codex", working_directory="/work")

    # Act
    command = backend.build_command("hello", session_id=None)

    # Assert
    assert command == [
        "codex",
        "exec",
        "--json",
        "--skip-git-repo-check",
        "-C",
        "/work",
        "hello",
    ]


def test_codex_backend_builds_resume_command() -> None:
    # Arrange
    backend = CodexCliBackend(codex_binary="codex", working_directory="/work")

    # Act
    command = backend.build_command("hello", session_id="thread-1")

    # Assert
    assert command == [
        "codex",
        "exec",
        "resume",
        "--json",
        "--skip-git-repo-check",
        "thread-1",
        "hello",
    ]


def test_codex_backend_normalizes_json_events() -> None:
    # Arrange
    parser = CodexCliBackend(
        codex_binary="codex", working_directory="/work"
    ).create_parser()

    # Act
    events = []
    events.extend(parser.parse({"type": "thread.started", "thread_id": "thread-1"}))
    events.extend(
        parser.parse(
            {
                "type": "item.completed",
                "item": {"type": "reasoning", "text": "checking"},
            }
        )
    )
    events.extend(
        parser.parse(
            {
                "type": "item.completed",
                "item": {
                    "type": "local_shell_call",
                    "command": "pytest",
                    "status": "completed",
                },
            }
        )
    )
    events.extend(
        parser.parse(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "answer"},
            }
        )
    )
    events.extend(
        parser.parse(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 11, "cached_input_tokens": 2},
            }
        )
    )

    # Assert
    assert [type(event).__name__ for event in events] == [
        "SystemEvent",
        "ThinkingEvent",
        "ToolUseEvent",
        "TextEvent",
        "ResultEvent",
    ]
    assert isinstance(events[0], SystemEvent)
    assert events[0].session_id == "thread-1"
    assert isinstance(events[1], ThinkingEvent)
    assert events[1].text == "checking"
    assert isinstance(events[2], ToolUseEvent)
    assert events[2].tool_name == "local_shell_call"
    assert events[2].tool_input["command"] == "pytest"
    assert isinstance(events[3], TextEvent)
    assert events[3].text == "answer"
    assert isinstance(events[4], ResultEvent)
    assert events[4].text == "answer"
    assert events[4].context_tokens == 13


def test_codex_backend_normalizes_started_command_events() -> None:
    # Arrange
    parser = CodexCliBackend(
        codex_binary="codex", working_directory="/work"
    ).create_parser()

    # Act
    events = []
    events.extend(
        parser.parse(
            {
                "type": "item.started",
                "item": {
                    "type": "command_execution",
                    "command": "/bin/bash -lc pytest",
                    "status": "in_progress",
                },
            }
        )
    )
    events.extend(
        parser.parse(
            {
                "type": "item.started",
                "item": {
                    "type": "mcp_tool_call",
                    "tool": "gmail_get_profile",
                    "arguments": {},
                },
            }
        )
    )
    events.extend(
        parser.parse(
            {
                "type": "item.started",
                "item": {
                    "type": "file_change",
                    "changes": [{"path": "/work/AGENTS.md", "kind": "edit"}],
                },
            }
        )
    )

    # Assert
    assert [type(event).__name__ for event in events] == [
        "ToolUseEvent",
        "ToolUseEvent",
        "ToolUseEvent",
    ]
    assert isinstance(events[0], ToolUseEvent)
    assert events[0].tool_name == "Bash"
    assert events[0].tool_input["command"] == "/bin/bash -lc pytest"
    assert isinstance(events[1], ToolUseEvent)
    assert events[1].tool_name == "gmail_get_profile"
    assert isinstance(events[2], ToolUseEvent)
    assert events[2].tool_name == "Edit"
    assert events[2].tool_input["file_path"] == "/work/AGENTS.md"


def test_backends_ignore_unknown_raw_events() -> None:
    # Arrange
    claude_parser = ClaudeCliBackend(claude_binary="claude").create_parser()
    codex_parser = CodexCliBackend(
        codex_binary="codex", working_directory="/work"
    ).create_parser()

    # Act / Assert
    assert claude_parser.parse({"type": "unknown"}) == []
    assert codex_parser.parse({"type": "unknown"}) == []
    assert codex_parser.parse({"type": "thread.started", "thread": "bad"}) == []
    assert codex_parser.parse({"type": "turn.completed", "turn": "bad"}) == []
