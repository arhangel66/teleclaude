## Why

The official Telegram MCP plugin is a one-way adapter — it cannot invoke Claude Code skills, manage sessions, show progress, or maintain context across messages. A dedicated bridge bot is needed to give full Claude Code access from a mobile device, with live progress feedback and persistent sessions.

## What Changes

- New Python bot (aiogram 3) that proxies Telegram messages to Claude Code CLI
- Spawns `claude -p --resume --output-format stream-json` subprocess per user message
- Parses NDJSON stream to show live progress (editable message) and final response (new message with push)
- Persists sessions in SQLite (chat_id → session_id mapping)
- `/new` command to reset session
- Whitelist-based authorization via `ALLOWED_CHAT_IDS` in `.env`
- Context size displayed in the footer of the final message (e.g. `15k`)

## Capabilities

### New Capabilities

- `telegram-bot`: Aiogram 3 bot setup, long-polling, message routing, authorization middleware
- `claude-runner`: Subprocess management, NDJSON stream parsing, event handling
- `session-management`: SQLite-based session store, `/new` command for session reset
- `telegram-ui`: Progress message editing (throttled), final message sending, context size footer

### Modified Capabilities

(none — this is a greenfield project)

## Impact

- New Python package with aiogram 3, aiosqlite dependencies
- Requires `claude` CLI available on PATH
- Uses `--dangerously-skip-permissions` flag (trusted users only)
- Single fixed working directory configured via `.env`
