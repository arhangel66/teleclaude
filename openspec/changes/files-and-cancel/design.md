## Context

Phase 1 (core-bridge) delivers text-only messaging. This change adds file support and cancel — the remaining Phase 1 MVP features from the PRD. The bot codebase already has claude_runner, telegram_ui, handlers, and session_store.

## Goals / Non-Goals

**Goals:**
- Accept photo, voice, video, document from Telegram, save locally, pass path to Claude
- Inline "Cancel" button on progress messages to kill the subprocess
- Forward slash-commands (e.g. `/standup`) to Claude as-is

**Non-Goals:**
- File format conversion (e.g. voice-to-text) — Claude handles that
- File size validation beyond Telegram's 20MB bot limit
- Auto-cleanup of downloaded files

## Decisions

### D1: File storage layout — flat per-chat directory

Files stored as `files/{chat_id}/{timestamp}_{filename}`. Simple, no nesting, easy to find manually.

### D2: File path injected into prompt text

No separate CLI flag — just prepend `"User sent a file: /abs/path\n\n{caption}"` to the prompt. Claude's Read tool can handle images, and skills handle audio/video.

### D3: Cancel via inline keyboard + subprocess reference

Add a single "Cancel" button to the progress message. On callback, look up the running subprocess by chat_id and send SIGTERM. Reuse the existing one-per-user subprocess tracking from claude_runner.

## Risks / Trade-offs

- **Large files slow to download** → Telegram limits bots to 20MB, acceptable
- **Cancel race condition** (subprocess finishes just as user presses Cancel) → Check if process is still alive before SIGTERM, ignore if already done
