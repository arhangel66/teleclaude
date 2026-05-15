## Context

The bot currently exposes a clean Telegram flow, but the execution service is Claude-specific: `ClaudeRunner` builds a `claude -p` command, parses Claude JSONL events, owns active subprocesses, and exposes normalized events to `run_prompt`. Codex uses a different CLI command shape and a different JSONL event schema, so adding it directly to `ClaudeRunner` would mix backend-specific parsing with shared subprocess lifecycle code.

The next deployment will run on a real server, so the implementation needs to be conservative: Claude remains the default backend, Codex is opt-in from `.env`, and session persistence must avoid mixing Claude session ids with Codex thread ids.

## Goals / Non-Goals

**Goals:**
- Select the prompt execution backend from `.env`.
- Preserve the current Telegram message handling, progress rendering, cancellation behavior, and final-answer delivery.
- Preserve existing Claude behavior by default.
- Add Codex support through normalized internal events.
- Make session persistence backend-aware.
- Drive implementation with tests before changing runtime behavior.

**Non-Goals:**
- Add a full multi-agent framework.
- Change Telegram UI modes or attachment prompt formatting.
- Support concurrent backends for the same message.
- Release or deploy to the server in this change; that is a follow-up step after tests pass locally.

## Decisions

### Use a small backend adapter boundary

Introduce a backend protocol with responsibility for command construction and raw JSONL parsing. Keep subprocess lifecycle, cancellation, timeout, stderr handling, and active-process tracking in one shared async runner.

Alternative considered: add `if backend == "codex"` branches to `ClaudeRunner`. That is simpler initially, but it keeps the class name and responsibilities misleading and makes every future backend touch the same code path.

### Keep one normalized event model

Keep the existing internal event types used by `run_prompt` and Telegram renderers: session, text, tool use, thinking, and result. Claude and Codex backends translate their raw JSONL into this shared model.

Claude mapping:
- `system.session_id` -> session event
- `assistant.message.content[].text` -> text event
- `assistant.message.content[].tool_use` -> tool event
- `assistant.message.content[].thinking` -> thinking event
- `result.result` plus usage -> result event

Codex mapping:
- `thread.started.thread_id` -> session event
- `item.completed` with `agent_message` -> text event and final text candidate
- `item.completed` with `local_shell_call`, `tool_call`, or `function_call` -> tool event
- `item.completed` with `reasoning`, `thought`, or `thinking` -> thinking event
- `turn.completed.usage` -> token accounting for the final result event

### Make sessions backend-aware

Change session persistence from one row per `chat_id` to one row per `(chat_id, backend)`. This allows the same Telegram chat to switch between Claude and Codex without resuming the wrong CLI conversation.

Migration should preserve existing rows as Claude sessions, because current deployments have only Claude-compatible session ids.

### Keep Claude compatibility settings

Add `AGENT_BACKEND=claude|codex`, defaulting to `claude`. Keep `CLAUDE_BINARY` and add `CODEX_BINARY`. Add optional shared model configuration only if it can be wired without changing current defaults.

Codex fresh command should use `codex exec --json --skip-git-repo-check -C <working_directory> <prompt>`. Codex resume command should use `codex exec resume --json --skip-git-repo-check <thread_id> <prompt>`. If dangerous permissions are still required for parity with current Claude behavior, expose that as explicit backend command construction rather than hiding it in Telegram code.

## Risks / Trade-offs

- Session migration could break existing resume behavior -> add tests for legacy rows and verify `/new` resets only the selected backend session.
- Codex JSONL schema may evolve -> keep parser defensive and ignore unknown events, matching current Claude parser behavior.
- Final Codex answer may not have a dedicated result event -> collect the latest `agent_message` and emit it when the turn completes or process exits.
- Codex resume command has no `-C` option -> rely on stored session identity for resumed context and run the subprocess from the configured working directory.
- Documentation currently references both Claude and Codex inconsistently -> update docs as part of implementation, but do not broaden the runtime scope beyond backend selection.

## Migration Plan

1. Add tests for the new backend contract and expected existing Claude behavior.
2. Introduce shared runner/backend modules while keeping `ClaudeRunner` import compatibility if needed.
3. Migrate session storage to include `backend`, preserving existing rows as `claude`.
4. Wire `.env` selection in construction.
5. Update `.env.example` and README.
6. Run the full test suite before any push or server release.

Rollback is straightforward: set `AGENT_BACKEND=claude` or revert to the previous runner wiring. Existing Claude sessions remain usable because migrated rows are stored under the `claude` backend.
