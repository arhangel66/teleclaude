## Context

The bot today has three streaming renderers in `src/bot/services/telegram_ui.py`:
- `VerboseRenderer` — one Telegram message per event. Cancel button migrates to the latest message. Produces a long stream of messages per prompt.
- `CompactRenderer` — one progress message edited in place, then **deleted** before the final answer is sent. The user sees the final answer but loses the log of what Claude did.
- `QuietRenderer` — only the final answer.

Event types coming from `ClaudeRunner` via `task_runner.run_prompt`:
- `TextEvent` — intermediate assistant text (not the final)
- `ToolUseEvent` — tool invocations (name + input)
- `ThinkingEvent` — extended thinking snippets
- `ResultEvent` — final answer + `context_tokens`

The user wants at most two Telegram messages per interaction: one persistent "log" message that collects thinking/tool/intermediate-text lines in a compact way, and one separate final-answer message.

## Goals / Non-Goals

**Goals:**
- Exactly two messages in the happy path: `[log]` and `[final answer]`.
- The log stays visible after the interaction completes (not deleted).
- The log is visually compact. Use Telegram MarkdownV2 **blockquote** formatting so the user's client can render it as a collapsed/indented section. Prefer *expandable blockquote* (`**>…||`) when supported so long logs stay one-click-away.
- Cancel button lives on the log message while Claude is running; removed when the final answer is emitted.
- Intermediate assistant text (`on_text`) goes into the log, not into the final answer position — the final answer is strictly the `ResultEvent.text`.
- Keep the existing renderer contract (`StreamRenderer` ABC) so `task_runner` and handlers don't change.
- Backwards compatible: `verbose`, `compact`, `quiet` modes remain selectable via `.env`.

**Non-Goals:**
- Changing the underlying Claude event stream shape.
- Rewriting `ProgressTracker` or touching `VerboseRenderer` behavior.
- Adding a UI for toggling the mode per-chat (config-only switch for now).
- Supporting rich inline formatting inside the log beyond blockquote + escaping.

## Decisions

### 1. Add a new renderer class `ThreadRenderer` rather than reshaping `CompactRenderer`

`CompactRenderer` deletes the progress message on `on_final`. Changing that in place would silently change the compact-mode UX for anyone relying on it. Introducing `ThreadRenderer` keeps modes orthogonal and gives us a clean diffable implementation. `build_renderer("thread", …)` returns the new class.

**Alternative considered:** extend `CompactRenderer` with a `preserve_progress: bool` flag. Rejected — produces a single class with two behaviors and worse testability.

### 2. Make `thread` the default `streaming_mode`

The user explicitly wants two-message UX. Change `Settings.streaming_mode` default from `verbose` to `thread`. `.env.example` updated accordingly.

### 3. Use Telegram MarkdownV2 **blockquote** for the log

Telegram renders `>` at line start as a blockquote and `**>…||` as an *expandable* blockquote (client-side collapses long content). This gives the "compact, doesn't bloat" UX the user asked for.

- Every log line is prefixed with `> ` after escaping.
- If the log has more than `EXPANDABLE_THRESHOLD` lines (e.g. 4), wrap it with `**>` opening and `||` closing to make it expandable.
- All user-facing dynamic text (tool arguments, thinking snippets) is MarkdownV2-escaped via a helper that escapes `_ * [ ] ( ) ~ ` > # + - = | { } . !` per the Telegram spec.
- Edits go through `edit_message_text(..., parse_mode="MarkdownV2")`. If the edit fails (e.g., invalid markdown somehow slipped through), fall back to plain-text edit without `parse_mode` so the bot never silently goes dark.

**Alternative considered:** HTML parse mode with `<blockquote expandable>`. Works too, but MarkdownV2 is already the established convention in most aiogram examples and the escape set is well-known; HTML would need its own escape helper. Either is acceptable — MarkdownV2 chosen for simplicity.

### 4. Single edited-in-place log message, throttled like `ProgressTracker`

Reuse the throttling pattern from `ProgressTracker`: hold a `_lines: list[str]`, re-render the full blockquote on change, edit at most every `THROTTLE_SECONDS` (2s) — with a final flush on `on_final` / `finish`. Avoids Telegram rate limits and "message not modified" errors.

### 5. Handle the 4096-char limit by tail-trimming

If the rendered blockquote exceeds `MAX_MESSAGE_LENGTH` (4096), drop oldest lines and prepend a single `> …` marker. Never spawn a second log message — that would break the "at most two messages" invariant. Log truncation events at `DEBUG`.

### 6. Intermediate `TextEvent` is treated as a log line, not a draft final

In verbose mode, `on_text` creates a message that can later be edited to become the final. In thread mode, the final comes exclusively from `ResultEvent` via `on_final`. Intermediate text lines are appended to the log (prefixed with a subtle marker, e.g. no emoji, to distinguish from thinking/tool lines), and `on_final` always sends a *new* message.

### 7. Cancel button placement

Cancel button stays on the log message through its lifetime. On `on_final`, remove the reply markup from the log message, then send the final answer as a plain second message. If the user cancels, the already-populated log remains in the chat as a record of partial progress.

## Risks / Trade-offs

- [MarkdownV2 escape bugs can break the edit] → implement a dedicated `_escape_md_v2` helper + unit tests, and wrap every edit in a try/except with plain-text fallback.
- [Long logs still get truncated and the user can't see early reasoning] → tail-trim with `…` marker; acceptable given the "at most two messages" invariant. An expandable blockquote mitigates scroll pain.
- [Older Telegram clients may render `**>…||` literally instead of expandable] → graceful: it still shows as a plain blockquote, just non-collapsible.
- [Telegram rejects edits of unchanged content with `message is not modified`] → swallowed in `TelegramUI.update_progress` already (try/except). Throttling also reduces incidence.
- [Final answer message has no cancel button and no footer link back to the log] → acceptable; they're adjacent messages. Footer token-count is still appended to the final answer like today.
- [Default change (`verbose` → `thread`) is user-visible] → documented in proposal; existing users can pin `streaming_mode=verbose` in `.env`.

## Migration Plan

1. Implement `ThreadRenderer` + `_escape_md_v2` + `build_renderer` branch.
2. Extend `TelegramUI.update_progress` to accept an optional `parse_mode` argument (default `None` keeps existing callers unchanged).
3. Add `"thread"` to `Settings.streaming_mode` literal, set it as the default, update `.env.example`.
4. Add unit tests (see tasks).
5. Deploy via `./deploy.sh` (project convention — auto-deploy after task).
6. Rollback: set `streaming_mode=verbose` (or `compact`) in `.env` on the VPS and restart; no DB changes, no data migration needed.

## Open Questions

- Should the expandable-blockquote wrapping kick in at a fixed line count or a fixed character count? Start with line count (4) and adjust after dogfooding.
- Do we want an optional separator line between "thinking" and "tool" blocks inside the log, or keep everything one flat list? Start flat; revisit if legibility becomes an issue.
