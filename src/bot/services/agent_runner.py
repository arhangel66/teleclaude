import asyncio
import json
import logging
from collections.abc import AsyncIterator

from src.bot.services.cli_backends import CliBackend, EventParser
from src.bot.services.runner_events import Event

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 600  # 10 minutes
_SILENT_ITEM_TYPES = {"command_execution", "file_change", "mcp_tool_call"}


def _is_known_silent_event(data: dict) -> bool:
    if data.get("type") == "turn.started":
        return True
    if data.get("type") == "item.completed":
        item = data.get("item")
        return isinstance(item, dict) and item.get("type") in _SILENT_ITEM_TYPES
    return False


class AgentRunner:
    def __init__(self, backend: CliBackend, working_directory: str) -> None:
        self._backend = backend
        self._cwd = working_directory
        self._active: dict[int, asyncio.subprocess.Process] = {}

    @property
    def backend_name(self) -> str:
        return self._backend.name

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
        cmd = self._backend.build_command(message, session_id)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
        )
        self._active[chat_id] = proc

        logger.info("Spawning %s: %s", self._backend.name, " ".join(cmd))

        try:
            assert proc.stdout is not None
            event_count = 0
            parser = self._backend.create_parser()
            async for event in self._parse_stream(proc.stdout, parser):
                event_count += 1
                logger.info("Event #%d: %s", event_count, event)
                yield event

            for event in parser.finalize():
                event_count += 1
                logger.info("Event #%d: %s", event_count, event)
                yield event

            await asyncio.wait_for(proc.wait(), timeout=30)
            logger.info(
                "%s exited with code %s (events=%d)",
                self._backend.name,
                proc.returncode,
                event_count,
            )

            if proc.returncode != 0 and proc.stderr:
                stderr = await proc.stderr.read()
                if stderr:
                    logger.error(
                        "%s stderr: %s",
                        self._backend.name,
                        stderr.decode(errors="replace")[:500],
                    )
        except asyncio.TimeoutError:
            logger.warning(
                "%s subprocess timeout for chat_id=%d",
                self._backend.name,
                chat_id,
            )
            proc.terminate()
            await proc.wait()
        finally:
            self._active.pop(chat_id, None)

    async def _parse_stream(
        self, stream: asyncio.StreamReader, parser: EventParser
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
            events = parser.parse(data)
            if events:
                for event in events:
                    yield event
            elif not _is_known_silent_event(data):
                logger.debug("Unhandled event type: %s", data.get("type"))
