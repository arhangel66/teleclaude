## 1. Tests First

- [x] 1.1 Add configuration tests for `AGENT_BACKEND` defaulting to Claude, accepting Codex, and rejecting unsupported values.
- [x] 1.2 Add Claude backend tests that preserve the current command construction and JSONL event parsing behavior.
- [x] 1.3 Add Codex backend tests for fresh command construction, resume command construction, `thread.started`, `item.completed`, and `turn.completed` parsing.
- [x] 1.4 Add session store tests for backend-aware `get`, `set`, `reset`, `list_chats`, and migration of existing rows to the Claude backend.
- [x] 1.5 Add `run_prompt` integration tests proving the selected backend session is loaded, stored, and delivered through the existing renderer callbacks.

## 2. Runner Architecture

- [x] 2.1 Extract shared runner event dataclasses into a backend-neutral module.
- [x] 2.2 Create a backend protocol and Claude CLI backend adapter.
- [x] 2.3 Create a Codex CLI backend adapter that normalizes Codex JSONL into the shared event model.
- [x] 2.4 Replace the Claude-specific subprocess runner with a shared async runner that owns active processes, timeout, stderr logging, and cancellation.
- [x] 2.5 Preserve compatibility for existing imports or update all call sites and tests to the new runner name.

## 3. Session Persistence

- [x] 3.1 Migrate the SQLite schema from `chat_id -> session_id` to `(chat_id, backend) -> session_id`.
- [x] 3.2 Treat existing pre-migration rows as Claude backend sessions.
- [x] 3.3 Update `/new` handling and scheduled task execution to reset or use the selected backend session.

## 4. Configuration and Wiring

- [x] 4.1 Add settings for backend selection, Codex binary, and any shared optional model/sandbox values needed by command construction.
- [x] 4.2 Build the selected backend in `construct.py` from `.env` settings.
- [x] 4.3 Ensure Claude remains the default with no `.env` changes.
- [x] 4.4 Ensure Codex uses `codex exec --json` for fresh runs and `codex exec resume --json` for resumed runs.

## 5. Documentation and Verification

- [x] 5.1 Update `.env.example` with Claude and Codex backend settings.
- [x] 5.2 Update README and project docs to describe backend selection and remove Claude/Codex naming drift where it affects setup.
- [x] 5.3 Run the full test suite with `uv run pytest tests/ -v`.
- [x] 5.4 Record any release-server prerequisites for the next step, including required CLI authentication and environment values.
