# Telegram Bridge Bot — PRD

## 1. Executive Summary

**Problem**: The official Telegram MCP plugin cannot invoke Claude Code skills, manage sessions, show progress, or schedule tasks. It's a one-way adapter, not a real bridge.

**Solution**: A Python bot (aiogram 3) that proxies Telegram messages to Claude Code CLI (`claude -p --resume --output-format stream-json`), parses the NDJSON stream for live progress, and sends results back. Each Telegram user gets an isolated session. Files (photos, video, voice, documents) are saved locally and passed as paths to Claude.

**Success Criteria**:
- All Claude Code skills accessible from Telegram without modification
- Live progress updates visible in Telegram within 2s of tool invocation
- Context size displayed in the last message (e.g. `15k`)
- File attachments (photo, video, voice, documents) delivered to Claude as local paths
- Scheduled tasks execute on cron and deliver results to the originating chat

---

## 2. User Experience & Functionality

### User Personas

| Persona | Description |
|---------|-------------|
| **Primary** | Mikhail — power user, uses Claude Code daily for dev work, wants mobile access to all skills |
| **Secondary** | Trusted teammates — whitelisted by chat_id in `.env`, same fixed working directory |

### User Stories

**US-1: Send a message**
As a user, I want to send a text message in Telegram and receive Claude's response, so that I can use Claude Code from my phone.

Acceptance Criteria:
- Bot receives text, invokes `claude -p "{text}" --resume {session_id} --output-format stream-json`
- Intermediate `assistant` text blocks appear as an **editable message** (no push notification)
- `tool_use` events shown as status line (e.g. `🔧 Bash: git status...`)
- Final response sent as a **new message** (push notification)
- Last message footer shows context size (e.g. `· 15k`)

**US-2: Send a file**
As a user, I want to send a photo, video, voice message, or document so that Claude can process it.

Acceptance Criteria:
- Bot downloads file to a persistent temp directory (e.g. `./files/{chat_id}/{timestamp}_{filename}`)
- File path is included in the prompt: `"User sent a file: /abs/path/to/file.jpg\n\n{caption or empty}"`
- Claude decides how to handle the file (Read for images, skill for audio/video)

**US-3: Reset session**
As a user, I want to type `/new` to start a fresh Claude session.

Acceptance Criteria:
- Bot generates a new session UUID for the chat_id
- Old session_id is discarded (not deleted from Claude's storage)
- Bot confirms: `"New session started."`

**US-4: Use skills**
As a user, I want to type `/standup` or any skill name and have Claude execute it.

Acceptance Criteria:
- Bot sends `claude -p "execute skill: daily-standup"` (or the exact user text)
- Works for any skill — bot doesn't need to know the skill list

**US-5: Cancel operation**
As a user, I want to cancel a long-running Claude operation.

Acceptance Criteria:
- Bot provides an inline "Cancel" button on the progress message
- Pressing it sends SIGTERM to the `claude` subprocess
- Bot confirms: `"Operation cancelled."`

### Non-Goals (v1)
- No inline/callback keyboards beyond "Cancel"
- No message history storage or search
- No per-user working directory (single fixed root)
- No MCP server passthrough
- No web UI or alternative interfaces
- Scheduled tasks — deferred to Phase 2

---

## 3. Technical Specifications

### Architecture

```
Telegram (aiogram 3 long-polling)
  │
  ▼
┌──────────────────────────────┐
│  Bot Process                 │
│                              │
│  MessageHandler              │
│  ├─ download files           │
│  ├─ spawn: claude -p ...     │
│  ├─ parse NDJSON stream      │
│  ├─ update TG message        │
│  └─ send final message       │
│                              │
│  SessionStore (SQLite)       │
│  └─ chat_id → session_id    │
│                              │
│  SubprocessManager           │
│  └─ chat_id → Process       │
│     (for cancel support)     │
└──────────────────────────────┘
```

### Claude CLI Invocation

```bash
claude -p "{message}" \
  --resume {session_id} \
  --output-format stream-json \
  --dangerously-skip-permissions
```

Working directory: fixed, configured in `.env`.

### NDJSON Stream Parsing

| Event type | Bot action |
|------------|------------|
| `system` | Extract `session_id`, store it |
| `assistant` (text) | Edit progress message in Telegram |
| `assistant` (tool_use) | Show tool name in progress message |
| `result` | Send **new message** with final text + context size footer |

Context size extraction: from `result` event, field `cost_usd` or token count if available. If not — estimate from message length.

### Telegram Message Update Strategy

1. On first `assistant` event → send a new message (this becomes the "progress message")
2. On subsequent `assistant`/`tool_use` events → **edit** the progress message (throttle: max 1 edit per 2 seconds to avoid Telegram rate limits)
3. On `result` event → send a **new message** (triggers push notification) with final text and context size in footer

### File Handling

```
./files/
  └── {chat_id}/
      └── {timestamp}_{original_filename}
```

- Photos: download largest resolution
- Voice: download as `.ogg`
- Video: download as `.mp4`
- Documents: download as-is
- Max file size: Telegram limit (20MB for bots)

### Data Storage (SQLite)

**Table: sessions**
| Column | Type | Description |
|--------|------|-------------|
| chat_id | INTEGER PK | Telegram chat ID |
| session_id | TEXT | Claude session UUID |
| created_at | TIMESTAMP | Session creation time |
| updated_at | TIMESTAMP | Last message time |

### Configuration (.env)

```env
TELEGRAM_BOT_TOKEN=...
ALLOWED_CHAT_IDS=123456,789012
WORKING_DIRECTORY=/Users/mikhail/w/learning/myagent
CLAUDE_BINARY=claude
FILES_DIR=./files
SQLITE_DB=./bot.db
```

### Security & Privacy

- **Authorization**: only `ALLOWED_CHAT_IDS` from `.env` can interact with the bot
- **Permissions**: `--dangerously-skip-permissions` (trusted users only)
- **File cleanup**: files persist (no auto-deletion) — manual cleanup as needed
- **No secrets in prompts**: bot never logs full prompts to stdout in production

---

## 4. Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.12+ | User preference, type hints |
| Bot framework | aiogram 3 | Async, modern, well-maintained |у
| DB | SQLite (aiosqlite) | Lightweight, no infra needed |
| Subprocess | asyncio.create_subprocess_exec | Non-blocking stream parsing |
| Deployment | systemd on VPS | Auto-restart, logging via journald |

### Project Structure

```
telegram-bridge/
├── pyproject.toml
├── .env
├── src/
│   └── bot/
│       ├── __init__.py
│       ├── main.py              # Entry point
│       ├── config.py            # Settings from .env
│       ├── construct.py         # DI: build all objects
│       ├── handlers/
│       │   ├── __init__.py
│       │   ├── message.py       # Text + file handler
│       │   └── commands.py      # /new, /cancel, /start
│       ├── services/
│       │   ├── __init__.py
│       │   ├── claude_runner.py # Subprocess + NDJSON parsing
│       │   ├── session_store.py # SQLite session management
│       │   ├── file_manager.py  # File download + storage
│       │   └── telegram_ui.py   # Message edit/send logic
│       └── models/
│           ├── __init__.py
│           └── events.py        # NDJSON event dataclasses
├── files/                       # Downloaded user files
└── bot.db                       # SQLite database
```

---

## 5. Risks & Roadmap

### Phase 1 — MVP
- Text message bridge with session persistence
- File handling (photo, video, voice, documents)
- Live progress updates (editable message + final new message)
- Context size in footer
- `/new` command for session reset
- Cancel button for long operations
- Whitelist-based authorization

### Phase 2 — Scheduled Tasks
- Schedule protocol (`json:schedule` blocks in Claude output)
- APScheduler with SQLite job store
- CRUD: create, list, delete scheduled tasks
- Scheduled task results delivered to originating chat

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Claude CLI subprocess hangs | Bot becomes unresponsive for that user | 10-minute timeout + SIGTERM, one subprocess per user |
| Telegram rate limits on message edits | 429 errors | Throttle edits to 1 per 2 seconds |
| Large Claude responses exceed TG message limit (4096 chars) | Message truncated | Split into multiple messages |
| `--dangerously-skip-permissions` security risk | Untrusted user could run destructive commands | Strict whitelist in `.env` |
| Session drift (Claude context grows unbounded) | Slow responses, high cost | Show context size, user manually `/new` |
