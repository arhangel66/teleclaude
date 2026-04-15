import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 600  # 10 minutes


@dataclass
class SystemEvent:
    session_id: str


@dataclass
class TextEvent:
    text: str


@dataclass
class ToolUseEvent:
    tool_name: str


@dataclass
class ThinkingEvent:
    text: str


@dataclass
class ResultEvent:
    text: str
    context_tokens: int


@dataclass
class _AssistantUsage:
    """Internal: carries usage from an assistant event; not yielded to callers."""
    tokens: int


Event = SystemEvent | TextEvent | ToolUseEvent | ThinkingEvent | ResultEvent


class ClaudeRunner:
    def __init__(self, claude_binary: str, working_directory: str) -> None:
        self._binary = claude_binary
        self._cwd = working_directory
        self._active: dict[int, asyncio.subprocess.Process] = {}

    def is_busy(self, chat_id: int) -> bool:
        return chat_id in self._active

    async def cancel(self, chat_id: int) -> bool:
        """Terminate running subprocess for chat_id. Returns True if killed."""
        proc = self._active.get(chat_id)
        if proc is None or proc.returncode is not None:
            return False
        proc.terminate()
        return True

    async def run(
        self, message: str, chat_id: int, session_id: str | None = None
    ) -> AsyncIterator[Event]:
        cmd = [
            self._binary,
            "-p", message,
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
        ]
        if session_id:
            cmd += ["--resume", session_id]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
        )
        self._active[chat_id] = proc

        logger.info("Spawning claude: %s", " ".join(cmd))

        try:
            assert proc.stdout is not None
            event_count = 0
            last_assistant_tokens = 0
            async for event in self._parse_stream(proc.stdout):
                event_count += 1
                if isinstance(event, _AssistantUsage):
                    last_assistant_tokens = event.tokens
                    continue
                if isinstance(event, ResultEvent) and last_assistant_tokens:
                    event = ResultEvent(text=event.text, context_tokens=last_assistant_tokens)
                logger.info("Event #%d: %s", event_count, event)
                yield event

            await asyncio.wait_for(proc.wait(), timeout=30)
            logger.info(
                "Claude exited with code %s (events=%d)", proc.returncode, event_count
            )

            if proc.returncode != 0 and proc.stderr:
                stderr = await proc.stderr.read()
                if stderr:
                    logger.error("Claude stderr: %s", stderr.decode()[:500])
        except asyncio.TimeoutError:
            logger.warning("Claude subprocess timeout for chat_id=%d", chat_id)
            proc.terminate()
            await proc.wait()
        finally:
            self._active.pop(chat_id, None)

    async def _parse_stream(
        self, stream: asyncio.StreamReader
    ) -> AsyncIterator[Event]:
        while True:
            try:
                line = await asyncio.wait_for(
                    stream.readline(), timeout=TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                break

            if not line:
                break

            text = line.decode().strip()
            if not text:
                continue

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                logger.debug("Skipping non-JSON line: %s", text[:100])
                continue

            logger.debug("Raw JSON: %s", text[:500])
            events = self._parse_event(data)
            if events:
                for event in events:
                    yield event
            else:
                logger.debug("Unhandled event type: %s", data.get("type"))

    def _parse_event(self, data: dict) -> list[Event]:
        event_type = data.get("type")

        if event_type == "system":
            session_id = data.get("session_id", "")
            if session_id:
                return [SystemEvent(session_id=session_id)]

        elif event_type == "assistant":
            message = data.get("message", {})
            out: list[Event] = []
            usage = message.get("usage", {})
            tokens = (
                usage.get("input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
            )
            if tokens:
                out.append(_AssistantUsage(tokens=tokens))
            for block in message.get("content", []):
                block_type = block.get("type")
                if block_type == "text":
                    out.append(TextEvent(text=block.get("text", "")))
                elif block_type == "tool_use":
                    out.append(ToolUseEvent(tool_name=block.get("name", "tool")))
                elif block_type == "thinking":
                    thinking_text = block.get("thinking") or block.get("text") or ""
                    if thinking_text:
                        out.append(ThinkingEvent(text=thinking_text))
            return out

        elif event_type == "result":
            result_text = data.get("result", "").strip()
            usage = data.get("usage", {})
            context_tokens = (
                usage.get("input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
            )
            return [ResultEvent(text=result_text, context_tokens=context_tokens)]

        return []
