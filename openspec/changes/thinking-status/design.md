## Context

Teleclaude is a Telegram bot bridging messages to Claude Code CLI. Currently, when a user sends a message, there is no visual feedback until the first `TextEvent` or `ToolUseEvent` arrives from the Claude subprocess. This can take several seconds, leaving the user uncertain.

Telegram provides `sendChatAction(action="typing")` which shows a "typing..." indicator for 5 seconds. It must be re-sent periodically to stay visible.

## Goals / Non-Goals

**Goals:**
- Show "typing" chat action immediately when a message is received
- Keep the indicator alive while Claude processes by re-sending every ~4s
- Stop cleanly when processing completes or errors out

**Non-Goals:**
- Custom status text (Telegram only supports predefined actions)
- Showing typing during file uploads or other non-text responses

## Decisions

### 1. Background task with asyncio

Use `asyncio.create_task` to run a loop that calls `send_chat_action("typing")` every 4 seconds. Cancel the task when processing ends.

**Why**: Simple, no new dependencies. The handler is already async and runs inside the event loop. A background task is cleaner than threading or callbacks.

**Alternative considered**: Sending the action inside the event stream loop on each event — rejected because events can be sparse (Claude may think for 10+ seconds before first event), so the typing indicator would expire.

### 2. Encapsulate in TelegramUI

Add a context manager or start/stop methods to `TelegramUI` for the typing indicator. This keeps Telegram-specific logic in one place.

**Why**: Follows existing pattern where `TelegramUI` owns all bot interactions.

## Risks / Trade-offs

- **[Rate limiting]** → `sendChatAction` is lightweight and not rate-limited by Telegram in practice. 4s interval is well within limits.
- **[Task cleanup]** → If the handler crashes, the typing task must be cancelled. Using `try/finally` ensures cleanup.
