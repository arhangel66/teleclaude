# TeleClaude

Telegram bot that bridges your chat into a local CLI coding agent — [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) by default, or Codex when selected in `.env`. Send text, photos, voice, video, or documents from Telegram and the selected CLI runs on your machine with access to its configured tools, skills, and MCP servers.

Think of it as a remote control for the same coding agent you use in the terminal, but over Telegram from anywhere.

![Demo — asking Claude to add pizza ingredients to a grocery basket](docs/screenshot.png)

## Why

Built as a replacement for [Openclaw](https://openclaw.ai/) after Anthropic blocked using Claude Code through third-party clients. You probably already have a CLI agent setup you love — with your own skills, MCP servers, project dirs, and login. TeleClaude exposes *that* setup over Telegram, without forcing you into someone else's client or a web UI you don't control. The native CLI stays the source of truth; Telegram is just the transport.

## Features

- Text, photo, voice (auto-transcribed), video, and document input
- Live streaming of agent thinking and tool calls into a single edited message
- Cancel button to interrupt a running task (SIGTERM to the subprocess)
- `/new` to start a fresh session for the selected backend; otherwise resumes the previous one per chat
- Slash commands (e.g. `/standup`) are forwarded to the selected agent as-is
- Per-chat allowlist — only whitelisted Telegram accounts can talk to the bot
- All files from Telegram are downloaded locally and their paths injected into the prompt

## Requirements

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager
- **Node.js 18+** — needed by Claude Code CLI
- The selected CLI backend installed and authenticated:
  - `claude` for the default Claude backend
  - `codex` for the Codex backend
- A **Telegram account** and a bot token
- An **OpenRouter API key** (only if you want voice transcription)

## Setup from scratch

### 1. Install a CLI backend

Claude is the default backend:

```bash
npm install -g @anthropic-ai/claude-code
claude login        # opens a browser to authenticate
claude --version    # sanity check
```

Run `claude` once interactively in the folder you plan to use as the bot's working directory — accept any first-run prompts (trust, etc.) so the subprocess won't hang later.

To use Codex instead, install and authenticate the Codex CLI, then set `AGENT_BACKEND=codex` in `.env`. The bot runs Codex through `codex exec --json` for new sessions and `codex exec resume --json` for resumed sessions.

### 2. Create a Telegram bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram, send `/newbot`, follow the prompts. Copy the token.
2. Open [@userinfobot](https://t.me/userinfobot) and copy your numeric chat id.

### 3. (Optional) Get an OpenRouter API key

Only needed if you want to send voice messages. Grab a key at [openrouter.ai/keys](https://openrouter.ai/keys). The default STT model is `google/gemini-3-flash-preview` — cheap and multilingual.

### 4. Clone and configure

```bash
git clone https://github.com/<your-fork>/teleclaude.git
cd teleclaude
cp .env.example .env
# edit .env — paste your token, chat id, and (optionally) OpenRouter key
uv sync
```

Set `WORKING_DIRECTORY` in `.env` to the folder you want the selected agent to operate on. It can be this repo, another project, or a blank scratch folder — whatever you want the agent to see.

Backend settings:

```env
AGENT_BACKEND=claude     # claude | codex
CLAUDE_BINARY=claude
CODEX_BINARY=codex
```

### 5. Run

```bash
uv run python -m src.bot.main
```

You should see `Bot started polling` in the logs. Now message your bot on Telegram.

## Usage

- `/start` — greeting, confirms you're on the allowlist
- `/new` — drop the current session for the selected backend and start fresh
- Any other message — forwarded to the selected CLI backend, response streams back
- Attach photos, voice notes, videos, or documents — they're downloaded and their paths are added to the prompt so the selected agent can inspect them
- Tap the **Cancel** button on the progress message to stop a running task

## Architecture

```
Telegram  ──▶  aiogram handlers  ──▶  AgentRunner  ──▶  selected CLI subprocess
                     ▲                    │
                     │                    ▼
                TelegramUI ◀──── normalized JSON event stream
```

- One CLI subprocess per user at a time
- Streaming JSON events are rendered as an edited blockquote message + a final answer
- Session ids are persisted per `(chat_id, backend)` in SQLite (`sessions.db`) so conversations survive restarts and Claude/Codex ids are not mixed
- File attachments are saved under `files/{chat_id}/{ts}_{name}` and path-injected into the prompt — no format conversion, the selected agent handles files through its own tools

Source layout:

```
src/bot/
  config.py        pydantic-settings loaded from .env
  construct.py     dependency injection — wires all services
  main.py          entrypoint: aiogram Dispatcher + polling
  handlers.py      /start, /new, messages, cancel callback
  services/
    agent_runner.py    shared subprocess lifecycle, cancellation, streaming
    cli_backends.py    Claude/Codex command construction and JSON normalization
    claude_runner.py   compatibility wrapper for ClaudeRunner imports
    telegram_ui.py     message send/edit + progress UI
    session_store.py   SQLite session persistence
    transcriber.py     voice → text via OpenRouter
    file_cleaner.py    background cleanup of old attachments
    scheduler.py       APScheduler setup
    task_runner.py     scheduled-task execution
```

## Scheduled tasks (optional)

You can have the selected agent run prompts on a cron schedule — morning digests, nightly maintenance, daily reminders, anything you'd normally type into the chat.

Copy the template and edit it:

```bash
cp scheduled_tasks.example.yaml scheduled_tasks.yaml
```

Each entry is a crontab expression plus a prompt. Minimal example:

```yaml
- name: morning-digest
  schedule: "0 8 * * *"
  timezone: Europe/Berlin
  prompt: "Summarize my PR review queue and Linear tickets due today."
  target: primary      # primary | all_sessions
  deliver: final       # final | silent
```

- `target: primary` — sends to the first id in `ALLOWED_CHAT_IDS`
- `target: all_sessions` — sends to every chat that ever used the bot
- `deliver: silent` — still runs the selected backend, but doesn't post the answer

Tasks are loaded on startup. If `scheduled_tasks.yaml` doesn't exist, the bot runs without scheduling — totally fine.

## Running on a server

There's no bundled deploy script — any long-running-process recipe works. Common options:

- **systemd** unit running `uv run python -m src.bot.main` with `WorkingDirectory=/path/to/teleclaude`
- **tmux / screen** session for quick setups
- **Docker** — not bundled, but a straightforward `python:3.13-slim` + `uv sync` + `node` image works

Whatever you pick, the server needs the selected CLI authenticated as the same user that runs the bot. For Claude, that means `claude` is installed and logged in. For Codex, that means `codex` is installed, logged in, and able to run `codex exec --json` in `WORKING_DIRECTORY`.

Before moving this to a release server, verify:

- `TELEGRAM_BOT_TOKEN`, `ALLOWED_CHAT_IDS`, `WORKING_DIRECTORY`, and `AGENT_BACKEND` are set in the server `.env`
- `CLAUDE_BINARY` or `CODEX_BINARY` points to the selected CLI on `PATH`
- the selected CLI has already completed interactive login/trust prompts as the service user

## Development

```bash
uv run pytest tests/ -v      # run tests
uv run ruff check src tests  # lint
uv run ruff format src tests # format
```

Tests are flat pytest functions following AAA, no test classes.

## License

MIT — see [LICENSE](LICENSE).
