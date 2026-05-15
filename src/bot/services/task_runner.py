import logging
from typing import Literal

from src.bot.services.runner_events import (
    ResultEvent,
    SystemEvent,
    TextEvent,
    ThinkingEvent,
    ToolUseEvent,
)
from src.bot.services.telegram_ui import StreamRenderer

logger = logging.getLogger(__name__)

Deliver = Literal["final", "silent"]

COMPACT_SUMMARY_PROMPT = """\
You are performing a context checkpoint compaction for a Telegram bridge session.
Create a concise handoff summary for a future agent that will resume this chat.

Include:
- the user's current goal and preferences
- important decisions and constraints
- current repository, deployment, and runtime facts
- completed work and pending next steps
- any blockers or caveats

Output only the summary. Do not answer as a normal assistant turn.
"""

COMPACT_SEED_PROMPT = """\
[chat_id={chat_id}]

This is a compacted context summary for this Telegram bridge session.
Treat it as background context for future turns and do not repeat it unless asked.

{summary}

Reply exactly: Context loaded.
"""


def _is_compact_command(prompt: str) -> bool:
    command = prompt.strip().split(maxsplit=1)[0] if prompt.strip() else ""
    return command == "/compact" or command.startswith("/compact@")


async def _capture_result(
    chat_id: int,
    prompt: str,
    *,
    claude_runner,
    session_id: str | None,
) -> tuple[str | None, str, int]:
    """Run the agent and capture only session/result events."""
    new_session_id: str | None = None
    result_text = ""
    context_tokens = 0

    async for event in claude_runner.run(prompt, chat_id, session_id):
        if isinstance(event, SystemEvent):
            new_session_id = event.session_id
        elif isinstance(event, ResultEvent):
            result_text = event.text
            context_tokens = event.context_tokens

    return new_session_id, result_text, context_tokens


async def _compact_session(
    chat_id: int,
    *,
    claude_runner,
    session_store,
    ui,
    backend: str,
    session_id: str | None,
    deliver: Deliver,
    renderer: StreamRenderer | None,
) -> None:
    if session_id is None:
        message = "No active session to compact."
        if renderer is not None:
            await renderer.on_final(message, 0)
        elif deliver == "final":
            await ui.send_text(chat_id, message)
        logger.info("compact chat=%d skipped: no active %s session", chat_id, backend)
        return

    _, summary, old_tokens = await _capture_result(
        chat_id,
        COMPACT_SUMMARY_PROMPT,
        claude_runner=claude_runner,
        session_id=session_id,
    )
    summary = summary.strip()
    if not summary:
        raise RuntimeError("compact summary was empty")

    seed_prompt = COMPACT_SEED_PROMPT.format(chat_id=chat_id, summary=summary)
    new_session_id, _, new_tokens = await _capture_result(
        chat_id,
        seed_prompt,
        claude_runner=claude_runner,
        session_id=None,
    )
    if not new_session_id:
        raise RuntimeError("compacted session did not return a session id")

    await session_store.set(chat_id, new_session_id, backend=backend)

    message = "Context compacted."
    if renderer is not None:
        await renderer.on_final(message, 0)
    elif deliver == "final":
        await ui.send_final(chat_id, message, 0)
    logger.info(
        "compact chat=%d ok (%s -> %s, old_tokens=%d, new_tokens=%d)",
        chat_id,
        session_id,
        new_session_id,
        old_tokens,
        new_tokens,
    )


async def run_prompt(
    chat_id: int,
    prompt: str,
    *,
    claude_runner,
    session_store,
    ui,
    deliver: Deliver = "final",
    start_typing: bool = True,
    renderer: StreamRenderer | None = None,
) -> None:
    """Send a prompt to the selected agent for the chat and stream events.

    If `renderer` is provided, TextEvent/ToolUseEvent/ThinkingEvent are routed
    through it (interactive UX). If `renderer` is None, those events are
    ignored (scheduled-task UX).

    `deliver` controls the final result:
      - 'final'  → ui.send_final(chat_id, text, tokens)
      - 'silent' → only log, nothing sent to Telegram
    """
    backend = getattr(claude_runner, "backend_name", "claude")
    if not isinstance(backend, str):
        backend = "claude"
    session_id = await session_store.get(chat_id, backend=backend)

    if _is_compact_command(prompt):
        typing_started = False
        if start_typing:
            await ui.start_typing(chat_id)
            typing_started = True
        try:
            await _compact_session(
                chat_id,
                claude_runner=claude_runner,
                session_store=session_store,
                ui=ui,
                backend=backend,
                session_id=session_id,
                deliver=deliver,
                renderer=renderer,
            )
        except Exception:
            logger.exception("compact failed for chat_id=%d", chat_id)
            if renderer is not None:
                await renderer.cleanup()
            elif deliver == "final":
                await ui.send_text(chat_id, "Error compacting session.")
        finally:
            if typing_started:
                await ui.stop_typing(chat_id)
        return

    if session_id is None:
        prompt = f"[chat_id={chat_id}]\n\n{prompt}"

    typing_started = False
    if start_typing:
        await ui.start_typing(chat_id)
        typing_started = True

    try:
        async for event in claude_runner.run(prompt, chat_id, session_id):
            if isinstance(event, SystemEvent):
                await session_store.set(
                    chat_id, event.session_id, backend=backend
                )
            elif isinstance(event, TextEvent):
                if renderer is not None:
                    await renderer.on_text(event.text)
            elif isinstance(event, ToolUseEvent):
                if renderer is not None:
                    await renderer.on_tool(event.tool_name, event.tool_input)
            elif isinstance(event, ThinkingEvent):
                if renderer is not None:
                    await renderer.on_thinking(event.text)
            elif isinstance(event, ResultEvent):
                if renderer is not None:
                    if deliver == "final":
                        await renderer.on_final(event.text, event.context_tokens)
                    else:
                        await renderer.finish()
                elif deliver == "final":
                    await ui.send_final(chat_id, event.text, event.context_tokens)
                if deliver == "final":
                    logger.info(
                        "task chat=%d delivered final (%d tokens)",
                        chat_id, event.context_tokens,
                    )
                else:
                    snippet = event.text[:200].replace("\n", " ")
                    logger.info(
                        "task chat=%d ok (%d tokens): %s",
                        chat_id, event.context_tokens, snippet,
                    )
    except Exception:
        logger.exception("run_prompt failed for chat_id=%d", chat_id)
        if renderer is not None:
            await renderer.cleanup()
    finally:
        if typing_started:
            await ui.stop_typing(chat_id)
