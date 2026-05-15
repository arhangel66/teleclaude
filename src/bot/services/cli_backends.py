from __future__ import annotations

from typing import Any, Protocol

from src.bot.services.runner_events import (
    Event,
    ResultEvent,
    SystemEvent,
    TextEvent,
    ThinkingEvent,
    ToolUseEvent,
)


class EventParser(Protocol):
    def parse(self, data: dict[str, Any]) -> list[Event]:
        ...

    def finalize(self) -> list[Event]:
        return []


class CliBackend(Protocol):
    name: str

    def build_command(self, message: str, session_id: str | None = None) -> list[str]:
        ...

    def create_parser(self) -> EventParser:
        ...


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _context_tokens(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0
    base = usage.get("input_tokens", usage.get("input_context_tokens", 0))
    return (
        _int_value(base)
        + _int_value(usage.get("cached_input_tokens"))
        + _int_value(usage.get("cache_read_input_tokens"))
        + _int_value(usage.get("cache_creation_input_tokens"))
    )


def _codex_context_tokens(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0
    if "input_tokens" in usage:
        return _int_value(usage.get("input_tokens"))
    if "input_context_tokens" in usage:
        return _int_value(usage.get("input_context_tokens"))
    return (
        _int_value(usage.get("cache_read_input_tokens"))
        + _int_value(usage.get("cache_creation_input_tokens"))
    )


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = (
                    item.get("text")
                    or item.get("output_text")
                    or item.get("content")
                    or ""
                )
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _extract_item_text(item: dict[str, Any]) -> str:
    for key in ("text", "output_text", "message", "summary"):
        text = _content_text(item.get(key))
        if text:
            return text
    return _content_text(item.get("content"))


class ClaudeEventParser:
    def __init__(self) -> None:
        self._last_assistant_tokens = 0

    def parse(self, data: dict[str, Any]) -> list[Event]:
        event_type = data.get("type")

        if event_type == "system":
            session_id = data.get("session_id", "")
            if session_id:
                return [SystemEvent(session_id=session_id)]

        if event_type == "assistant":
            message = data.get("message", {})
            if not isinstance(message, dict):
                return []
            tokens = _context_tokens(message.get("usage", {}))
            if tokens:
                self._last_assistant_tokens = tokens

            out: list[Event] = []
            content = message.get("content", [])
            if not isinstance(content, list):
                return []
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    out.append(TextEvent(text=block.get("text", "")))
                elif block_type == "tool_use":
                    out.append(
                        ToolUseEvent(
                            tool_name=block.get("name", "tool"),
                            tool_input=block.get("input") or {},
                        )
                    )
                elif block_type == "thinking":
                    thinking_text = block.get("thinking") or block.get("text") or ""
                    if thinking_text:
                        out.append(ThinkingEvent(text=thinking_text))
            return out

        if event_type == "result":
            result_text = data.get("result", "").strip()
            context_tokens = _context_tokens(data.get("usage", {}))
            if context_tokens == 0:
                context_tokens = self._last_assistant_tokens
            return [ResultEvent(text=result_text, context_tokens=context_tokens)]

        return []

    def finalize(self) -> list[Event]:
        return []


class ClaudeCliBackend:
    name = "claude"

    def __init__(self, claude_binary: str) -> None:
        self._binary = claude_binary

    def build_command(self, message: str, session_id: str | None = None) -> list[str]:
        cmd = [
            self._binary,
            "-p",
            message,
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
        ]
        if session_id:
            cmd += ["--resume", session_id]
        return cmd

    def create_parser(self) -> ClaudeEventParser:
        return ClaudeEventParser()


class CodexEventParser:
    _TOOL_TYPES = {"local_shell_call", "tool_call", "function_call"}
    _START_TOOL_TYPES = {"command_execution", "mcp_tool_call", "file_change"}
    _THINKING_TYPES = {"reasoning", "thought", "thinking"}

    def __init__(self) -> None:
        self._last_agent_text: str | None = None
        self._last_context_tokens = 0
        self._result_emitted = False

    def parse(self, data: dict[str, Any]) -> list[Event]:
        event_type = data.get("type")

        if event_type == "thread.started":
            thread = data.get("thread", {})
            thread_id = thread.get("id") if isinstance(thread, dict) else None
            session_id = data.get("thread_id") or thread_id
            if session_id:
                return [SystemEvent(session_id=session_id)]

        if event_type == "item.started":
            item = data.get("item", {})
            if not isinstance(item, dict):
                return []
            item_type = item.get("type", "")
            if item_type in self._START_TOOL_TYPES:
                return [self._tool_event_from_started_item(item, item_type)]

        if event_type == "item.completed":
            item = data.get("item", {})
            if not isinstance(item, dict):
                return []
            item_type = item.get("type", "")

            if item_type == "agent_message":
                text = _extract_item_text(item)
                if not text:
                    return []
                self._last_agent_text = text
                return [TextEvent(text=text)]

            if item_type in self._THINKING_TYPES:
                text = _extract_item_text(item)
                if text:
                    return [ThinkingEvent(text=text)]
                return []

            if item_type in self._TOOL_TYPES:
                tool_name = item.get("name") or item_type
                tool_input = {
                    key: value
                    for key, value in item.items()
                    if key not in {"type", "name"}
                }
                explicit_input = item.get("input")
                if isinstance(explicit_input, dict):
                    tool_input = explicit_input
                return [ToolUseEvent(tool_name=tool_name, tool_input=tool_input)]

        if event_type == "turn.completed":
            turn = data.get("turn", {})
            turn_usage = turn.get("usage", {}) if isinstance(turn, dict) else {}
            usage = data.get("usage") or turn_usage
            self._last_context_tokens = _codex_context_tokens(usage)
            if self._last_agent_text is None:
                return []
            self._result_emitted = True
            return [
                ResultEvent(
                    text=self._last_agent_text.strip(),
                    context_tokens=self._last_context_tokens,
                )
            ]

        return []

    def _tool_event_from_started_item(
        self, item: dict[str, Any], item_type: str
    ) -> ToolUseEvent:
        if item_type == "command_execution":
            return ToolUseEvent(
                tool_name="Bash",
                tool_input={"command": item.get("command", "")},
            )
        if item_type == "mcp_tool_call":
            arguments = item.get("arguments")
            tool_input = arguments if isinstance(arguments, dict) else {}
            return ToolUseEvent(
                tool_name=str(item.get("tool") or "mcp_tool_call"),
                tool_input=tool_input,
            )
        if item_type == "file_change":
            changes = item.get("changes")
            path = ""
            if isinstance(changes, list) and changes:
                first = changes[0]
                if isinstance(first, dict):
                    path = str(first.get("path") or "")
            return ToolUseEvent(
                tool_name="Edit",
                tool_input={"file_path": path, "changes": changes or []},
            )
        return ToolUseEvent(tool_name=item_type, tool_input={})

    def finalize(self) -> list[Event]:
        if self._last_agent_text is None or self._result_emitted:
            return []
        self._result_emitted = True
        return [
            ResultEvent(
                text=self._last_agent_text.strip(),
                context_tokens=self._last_context_tokens,
            )
        ]


class CodexCliBackend:
    name = "codex"

    def __init__(self, codex_binary: str, working_directory: str) -> None:
        self._binary = codex_binary
        self._working_directory = working_directory

    def build_command(self, message: str, session_id: str | None = None) -> list[str]:
        if session_id:
            return [
                self._binary,
                "exec",
                "resume",
                "--json",
                "--skip-git-repo-check",
                session_id,
                message,
            ]
        return [
            self._binary,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "-C",
            self._working_directory,
            message,
        ]

    def create_parser(self) -> CodexEventParser:
        return CodexEventParser()
