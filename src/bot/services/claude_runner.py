from src.bot.services.agent_runner import AgentRunner
from src.bot.services.cli_backends import ClaudeCliBackend
from src.bot.services.runner_events import (
    Event,
    ResultEvent,
    SystemEvent,
    TextEvent,
    ThinkingEvent,
    ToolUseEvent,
)


class ClaudeRunner(AgentRunner):
    def __init__(self, claude_binary: str, working_directory: str) -> None:
        super().__init__(
            backend=ClaudeCliBackend(claude_binary=claude_binary),
            working_directory=working_directory,
        )

    def _parse_event(self, data: dict) -> list[Event]:
        return ClaudeCliBackend(claude_binary="claude").create_parser().parse(data)
