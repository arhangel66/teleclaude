import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.bot.services.task_runner import run_prompt

logger = logging.getLogger(__name__)

Target = Literal["primary", "all_sessions"]
Deliver = Literal["final", "silent"]


@dataclass(frozen=True)
class ScheduledTask:
    name: str
    schedule: str
    timezone: str
    prompt: str
    target: Target
    deliver: Deliver


def load_tasks(path: Path) -> list[ScheduledTask]:
    """Load scheduled tasks from YAML. Missing file → []."""
    if not path.exists():
        logger.info("scheduled_tasks file not found at %s — no scheduled tasks", path)
        return []

    raw = yaml.safe_load(path.read_text()) or []
    if not isinstance(raw, list):
        raise ValueError(f"{path}: top-level must be a list, got {type(raw).__name__}")

    tasks: list[ScheduledTask] = []
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}[{idx}]: entry must be a mapping")
        try:
            task = ScheduledTask(
                name=entry["name"],
                schedule=entry["schedule"],
                timezone=entry.get("timezone", "UTC"),
                prompt=entry["prompt"],
                target=entry.get("target", "primary"),
                deliver=entry.get("deliver", "final"),
            )
        except KeyError as exc:
            raise ValueError(f"{path}[{idx}]: missing required field {exc}") from exc
        if task.target not in ("primary", "all_sessions"):
            raise ValueError(f"{path}[{idx}]: invalid target={task.target!r}")
        if task.deliver not in ("final", "silent"):
            raise ValueError(f"{path}[{idx}]: invalid deliver={task.deliver!r}")
        tasks.append(task)
    return tasks


class TaskScheduler:
    def __init__(
        self,
        tasks: list[ScheduledTask],
        settings,
        claude_runner,
        session_store,
        ui,
    ) -> None:
        self._tasks = tasks
        self._settings = settings
        self._claude_runner = claude_runner
        self._session_store = session_store
        self._ui = ui
        self._scheduler = AsyncIOScheduler()
        for task in tasks:
            self._register(task)

    def _register(self, task: ScheduledTask) -> None:
        try:
            trigger = CronTrigger.from_crontab(task.schedule, timezone=task.timezone)
        except Exception:
            logger.exception("scheduled %s: invalid cron/timezone, skipping", task.name)
            return
        self._scheduler.add_job(
            self._run,
            trigger=trigger,
            args=[task],
            id=task.name,
            misfire_grace_time=300,
            replace_existing=True,
        )
        logger.info(
            "scheduled %s at '%s' (%s) target=%s deliver=%s",
            task.name, task.schedule, task.timezone, task.target, task.deliver,
        )

    async def _resolve_targets(self, task: ScheduledTask) -> list[int]:
        if task.target == "primary":
            allowed = self._settings.allowed_chat_ids
            if not allowed:
                return []
            return [allowed[0]]
        return await self._session_store.list_chats()

    async def _run(self, task: ScheduledTask) -> None:
        targets = await self._resolve_targets(task)
        for chat_id in targets:
            if self._claude_runner.is_busy(chat_id):
                logger.warning(
                    "scheduled %s: chat %d busy, skipped", task.name, chat_id
                )
                continue
            try:
                await run_prompt(
                    chat_id,
                    task.prompt,
                    claude_runner=self._claude_runner,
                    session_store=self._session_store,
                    ui=self._ui,
                    deliver=task.deliver,
                    start_typing=task.deliver == "final",
                )
            except Exception:
                logger.exception(
                    "scheduled %s: run_prompt failed for chat %d", task.name, chat_id
                )

    def start(self) -> None:
        self._scheduler.start()

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
