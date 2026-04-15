import logging
from typing import Literal

from src.bot.services.claude_runner import (
    ResultEvent,
    SystemEvent,
    TextEvent,
    ThinkingEvent,
    ToolUseEvent,
)
from src.bot.services.telegram_ui import StreamRenderer

logger = logging.getLogger(__name__)

Deliver = Literal["final", "silent"]


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
    """Send a prompt to Claude for the given chat, resume session, stream events.

    If `renderer` is provided, TextEvent/ToolUseEvent/ThinkingEvent are routed
    through it (interactive UX). If `renderer` is None, those events are
    ignored (scheduled-task UX).

    `deliver` controls the final result:
      - 'final'  → ui.send_final(chat_id, text, tokens)
      - 'silent' → only log, nothing sent to Telegram
    """
    session_id = await session_store.get(chat_id)
    if session_id is None:
        prompt = f"[chat_id={chat_id}]\n\n{prompt}"

    typing_started = False
    if start_typing:
        await ui.start_typing(chat_id)
        typing_started = True

    try:
        async for event in claude_runner.run(prompt, chat_id, session_id):
            if isinstance(event, SystemEvent):
                await session_store.set(chat_id, event.session_id)
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
