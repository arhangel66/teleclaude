## Why

TeleClaude currently routes every prompt through the Claude CLI contract, which blocks running the same Telegram workflow with Codex. We need a small runner abstraction now so the bot can select Claude or Codex from `.env` while preserving the existing Telegram UX, cancellation, sessions, attachments, and streaming behavior.

## What Changes

- Add a CLI backend boundary for `run_prompt` so Telegram code consumes normalized runner events instead of Claude-specific JSONL.
- Keep the existing Claude behavior as the default and preserve backward compatibility for current `.env` deployments.
- Add a Codex CLI backend selected from `.env`, using `codex exec --json` for fresh runs and `codex exec resume` for resumed sessions.
- Store sessions in a backend-aware way so Claude session ids and Codex thread ids cannot be mixed.
- Cover the change with tests first: command construction, JSONL parsing, backend selection, session isolation, and `run_prompt` integration.
- Update user-facing setup docs and example environment values to describe both supported backends.

## Capabilities

### New Capabilities
- `cli-agent-backend-selection`: Configure the Telegram bridge to execute prompts through either Claude CLI or Codex CLI while exposing the same normalized progress/final-response behavior to the rest of the application.

### Modified Capabilities

## Impact

- Affected code: `src/bot/config.py`, `src/bot/construct.py`, `src/bot/services/claude_runner.py` or its replacement, `src/bot/services/task_runner.py`, `src/bot/services/session_store.py`, `.env.example`, and README/project docs.
- Affected tests: runner/parser tests, session store tests, prompt/task runner tests, and configuration tests.
- Runtime impact: existing Claude deployments should continue working without `.env` changes; Codex deployments will require the local `codex` CLI to be installed and authenticated on the server.
