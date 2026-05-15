import logging
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.services.claude_runner import ResultEvent, SystemEvent, TextEvent
from src.bot.services.scheduler import ScheduledTask, TaskScheduler, load_tasks


YAML_TWO_TASKS = """
- name: daily_standup
  schedule: "0 7 * * *"
  timezone: Asia/Tbilisi
  prompt: "/daily-standup"
  target: primary
  deliver: final

- name: nightly_compact
  schedule: "0 3 * * *"
  timezone: Asia/Tbilisi
  prompt: "/compact"
  target: all_sessions
  deliver: silent
"""


def test_load_tasks_parses_yaml(tmp_path: Path) -> None:
    p = tmp_path / "scheduled_tasks.yaml"
    p.write_text(YAML_TWO_TASKS)

    tasks = load_tasks(p)

    assert len(tasks) == 2
    standup, compact = tasks
    assert standup == ScheduledTask(
        name="daily_standup",
        schedule="0 7 * * *",
        timezone="Asia/Tbilisi",
        prompt="/daily-standup",
        target="primary",
        deliver="final",
    )
    assert compact == ScheduledTask(
        name="nightly_compact",
        schedule="0 3 * * *",
        timezone="Asia/Tbilisi",
        prompt="/compact",
        target="all_sessions",
        deliver="silent",
    )


def test_load_tasks_missing_file_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.yaml"

    tasks = load_tasks(missing)

    assert tasks == []


def test_load_tasks_defaults_target_and_deliver(tmp_path: Path) -> None:
    p = tmp_path / "minimal.yaml"
    p.write_text(
        '- name: t1\n  schedule: "*/5 * * * *"\n  prompt: "hi"\n'
    )

    tasks = load_tasks(p)

    assert len(tasks) == 1
    assert tasks[0].target == "primary"
    assert tasks[0].deliver == "final"
    assert tasks[0].timezone == "UTC"


@dataclass
class _StubSettings:
    allowed_chat_ids: list[int]


def _make_scheduler(
    task: ScheduledTask,
    *,
    allowed_chat_ids: list[int] | None = None,
    session_chats: list[int] | None = None,
    busy_chats: set[int] | None = None,
) -> tuple[TaskScheduler, MagicMock, MagicMock, MagicMock]:
    settings = _StubSettings(allowed_chat_ids=allowed_chat_ids or [42])
    claude_runner = MagicMock()
    claude_runner.is_busy = MagicMock(
        side_effect=lambda cid: cid in (busy_chats or set())
    )
    session_store = MagicMock()
    session_store.list_chats = AsyncMock(return_value=session_chats or [])
    ui = MagicMock()
    scheduler = TaskScheduler(
        tasks=[task],
        settings=settings,
        claude_runner=claude_runner,
        session_store=session_store,
        ui=ui,
    )
    return scheduler, claude_runner, session_store, ui


@pytest.mark.asyncio
async def test_primary_task_uses_first_allowed_chat() -> None:
    task = ScheduledTask(
        name="t", schedule="0 7 * * *", timezone="UTC",
        prompt="/p", target="primary", deliver="final",
    )
    scheduler, _, _, _ = _make_scheduler(task, allowed_chat_ids=[111, 222])

    with patch("src.bot.services.scheduler.run_prompt", new_callable=AsyncMock) as mock_run:
        await scheduler._run(task)

    mock_run.assert_awaited_once()
    kwargs = mock_run.await_args.kwargs
    args = mock_run.await_args.args
    assert args[0] == 111
    assert args[1] == "/p"
    assert kwargs["deliver"] == "final"


@pytest.mark.asyncio
async def test_all_sessions_task_iterates_session_chats() -> None:
    task = ScheduledTask(
        name="t", schedule="0 3 * * *", timezone="UTC",
        prompt="/compact", target="all_sessions", deliver="silent",
    )
    scheduler, _, _, _ = _make_scheduler(task, session_chats=[1, 2])

    with patch("src.bot.services.scheduler.run_prompt", new_callable=AsyncMock) as mock_run:
        await scheduler._run(task)

    assert mock_run.await_count == 2
    chat_ids = [call.args[0] for call in mock_run.await_args_list]
    assert chat_ids == [1, 2]


@pytest.mark.asyncio
async def test_primary_busy_skips_task(caplog) -> None:
    task = ScheduledTask(
        name="t", schedule="0 7 * * *", timezone="UTC",
        prompt="/p", target="primary", deliver="final",
    )
    scheduler, _, _, _ = _make_scheduler(
        task, allowed_chat_ids=[5], busy_chats={5}
    )

    with patch("src.bot.services.scheduler.run_prompt", new_callable=AsyncMock) as mock_run:
        with caplog.at_level(logging.WARNING, logger="src.bot.services.scheduler"):
            await scheduler._run(task)

    mock_run.assert_not_awaited()
    assert any("busy" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_per_chat_busy_skip_for_all_sessions() -> None:
    task = ScheduledTask(
        name="t", schedule="0 3 * * *", timezone="UTC",
        prompt="/c", target="all_sessions", deliver="silent",
    )
    scheduler, _, _, _ = _make_scheduler(
        task, session_chats=[1, 2], busy_chats={1}
    )

    with patch("src.bot.services.scheduler.run_prompt", new_callable=AsyncMock) as mock_run:
        await scheduler._run(task)

    assert mock_run.await_count == 1
    assert mock_run.await_args.args[0] == 2


@pytest.mark.asyncio
async def test_deliver_final_sends_to_telegram() -> None:
    from src.bot.services.task_runner import run_prompt

    async def fake_run(*_a, **_kw):
        yield SystemEvent(session_id="sess-1")
        yield TextEvent(text="hi")
        yield ResultEvent(text="done", context_tokens=1234)

    claude_runner = MagicMock()
    claude_runner.run = fake_run
    session_store = MagicMock()
    session_store.get = AsyncMock(return_value=None)
    session_store.set = AsyncMock()
    ui = MagicMock()
    ui.start_typing = AsyncMock()
    ui.stop_typing = AsyncMock()
    ui.send_final = AsyncMock()

    await run_prompt(
        chat_id=7,
        prompt="/daily-standup",
        claude_runner=claude_runner,
        session_store=session_store,
        ui=ui,
        deliver="final",
    )

    ui.send_final.assert_awaited_once_with(7, "done", 1234)
    session_store.set.assert_awaited_once_with(7, "sess-1", backend="claude")


@pytest.mark.asyncio
async def test_deliver_silent_does_not_send_to_telegram(caplog) -> None:
    from src.bot.services.task_runner import run_prompt

    async def fake_run(*_a, **_kw):
        yield SystemEvent(session_id="sess-42")
        yield ResultEvent(text="quiet-ok", context_tokens=500)

    claude_runner = MagicMock()
    claude_runner.run = fake_run
    session_store = MagicMock()
    session_store.get = AsyncMock(return_value="sess-42")
    session_store.set = AsyncMock()
    ui = MagicMock()
    ui.start_typing = AsyncMock()
    ui.stop_typing = AsyncMock()
    ui.send_final = AsyncMock()

    with caplog.at_level(logging.INFO, logger="src.bot.services.task_runner"):
        await run_prompt(
            chat_id=9,
            prompt="/daily-standup",
            claude_runner=claude_runner,
            session_store=session_store,
            ui=ui,
            deliver="silent",
            start_typing=False,
        )

    ui.send_final.assert_not_awaited()
    assert any(
        "task" in rec.message.lower() and "ok" in rec.message.lower()
        for rec in caplog.records
    )
