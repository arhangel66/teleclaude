## Context

There is no existing bot infrastructure. This is a greenfield Python project. The Claude Code CLI supports `--output-format stream-json` which emits NDJSON events (`system`, `assistant`, `result`) that can be parsed in real-time. Aiogram 3 provides async handlers and Telegram Bot API integration. The bot will run on a VPS with systemd.

## Goals / Non-Goals

**Goals:**
- Reliable text message bridge: Telegram → Claude CLI → Telegram
- Live progress feedback via editable Telegram messages
- Session persistence across messages (resume conversations)
- Simple authorization via chat ID whitelist
- Context size visibility in message footer

**Non-Goals:**
- File handling (photos, video, voice, documents) — Phase 2
- Cancel button for long operations — Phase 2
- Scheduled tasks — Phase 2
- Per-user working directories
- Web UI or alternative interfaces
- MCP server passthrough

## Decisions

### D1: Aiogram 3 with long-polling (not webhooks)

Long-polling is simpler to deploy — no HTTPS certificate, no public URL, no nginx. For a single-user bot, the latency difference is negligible.

**Alternative**: Webhooks — better for high-traffic bots, but adds deployment complexity.

### D2: One subprocess per message, not a persistent Claude process

Each user message spawns a new `claude -p` subprocess with `--resume {session_id}`. The `--resume` flag maintains conversation context across invocations. This avoids managing long-lived processes and stdin/stdout multiplexing.

**Alternative**: Keep a persistent Claude process per user — more complex, harder to recover from crashes, marginal latency benefit.

### D3: SQLite via aiosqlite for session storage

Lightweight, zero-config, file-based. Perfect for a single-instance bot. The only data stored is the chat_id → session_id mapping.

**Alternative**: In-memory dict — loses sessions on restart.

### D4: Throttled message edits (max 1 per 2 seconds)

Telegram rate-limits `editMessageText`. We buffer intermediate events and flush the latest state every 2 seconds. This avoids 429 errors while still providing near-real-time feedback.

### D5: DI via construct.py

All service objects instantiated in `construct.py`, following the user's preferred pattern. Config loaded from `.env` via pydantic-settings or similar.

### D6: Project structure

```
src/
└── bot/
    ├── main.py           # Entry point (long-polling)
    ├── config.py          # Settings from .env
    ├── construct.py       # DI: build all objects
    ├── handlers/
    │   ├── message.py     # Text message handler
    │   └── commands.py    # /new, /start
    ├── services/
    │   ├── claude_runner.py  # Subprocess + NDJSON parsing
    │   ├── session_store.py  # SQLite session management
    │   └── telegram_ui.py    # Message edit/send with throttling
    └── models/
        └── events.py      # NDJSON event dataclasses
```

## Risks / Trade-offs

- **Claude CLI subprocess hangs** → 10-minute timeout with SIGTERM, one subprocess per user at a time
- **Telegram rate limits on edits** → 2-second throttle on `editMessageText`
- **Large responses exceed 4096 char limit** → Split into multiple messages
- **`--dangerously-skip-permissions` security** → Strict whitelist mitigates this; only trusted users
- **Session context grows unbounded** → Context size in footer helps user decide when to `/new`
