from dataclasses import dataclass, field


@dataclass
class SystemEvent:
    session_id: str


@dataclass
class TextEvent:
    text: str


@dataclass
class ToolUseEvent:
    tool_name: str
    tool_input: dict = field(default_factory=dict)


@dataclass
class ThinkingEvent:
    text: str


@dataclass
class ResultEvent:
    text: str
    context_tokens: int


Event = SystemEvent | TextEvent | ToolUseEvent | ThinkingEvent | ResultEvent
