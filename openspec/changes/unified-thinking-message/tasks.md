## 1. Config

- [x] 1.1 Add `"thread"` to `Settings.streaming_mode` `Literal` in `src/bot/config.py` and change default to `"thread"`
- [x] 1.2 Update `.env.example` default to `streaming_mode=thread` and add a comment listing the other options

## 2. Telegram UI primitives

- [x] 2.1 Add `_escape_md_v2(text: str) -> str` helper in `src/bot/services/telegram_ui.py` that escapes `_ * [ ] ( ) ~ \` > # + - = | { } . !` per MarkdownV2 spec
- [x] 2.2 Extend `TelegramUI.update_progress` with an optional `parse_mode: str | None = None` kwarg and pass it through to `edit_message_text`; keep existing callers unchanged
- [x] 2.3 Add `TelegramUI.update_progress_md` (or a thin wrapper) that calls `update_progress` with `parse_mode="MarkdownV2"` and, on failure, retries once without `parse_mode` as a plain-text fallback; log the failure at `DEBUG`

## 3. ThreadRenderer

- [x] 3.1 Add `ThreadRenderer(StreamRenderer)` in `src/bot/services/telegram_ui.py` with:
      - `_lines: list[str]` holding escaped log entries (thinking / tool / intermediate-text)
      - `_message_id: int | None`, `_last_edit: float`, `_pending_text: str | None`
- [x] 3.2 Implement `on_thinking(text)` → append a single-line thinking snippet (prefixed with `THINKING_PREFIX`, escaped) and flush
- [x] 3.3 Implement `on_tool(name, input)` → append `_format_tool_line(...)` (escaped) and flush
- [x] 3.4 Implement `on_text(text)` → append the intermediate assistant text as a non-prefixed log line (escaped) and flush; do NOT treat it as a final
- [x] 3.5 Implement `_flush()` reusing the throttling pattern from `ProgressTracker` (2s interval, final flush via `finish`)
- [x] 3.6 Implement `_render_block(lines)` that joins escaped lines with `\n`, tail-trims if over `MAX_MESSAGE_LENGTH`, prepends `> …` truncation marker on trim, wraps with expandable-blockquote syntax when `len(lines) > EXPANDABLE_THRESHOLD` (default 4), and ensures every line starts with `> `
- [x] 3.7 Implement `on_final(text, context_tokens)`:
      1. final flush of the log
      2. remove inline keyboard from the log message
      3. `ui.send_final(chat_id, text, context_tokens)` — sent as a new message
- [x] 3.8 Implement `finish()` and `cleanup()` to flush the log and strip the cancel keyboard without deleting the message
- [x] 3.9 Register `"thread"` in `build_renderer(mode, ui, chat_id)` returning a `ThreadRenderer`

## 4. Tests

- [x] 4.1 `tests/test_telegram_ui.py`: `_escape_md_v2` escapes each reserved char exactly once
- [x] 4.2 `tests/test_telegram_ui.py`: `ThreadRenderer.on_thinking`/`on_tool`/`on_text` append to the log and edit in place (assert single `send_message` call, ≥1 `edit_message_text` call with `parse_mode="MarkdownV2"`)
- [x] 4.3 `tests/test_telegram_ui.py`: `ThreadRenderer.on_final` sends a NEW message containing `ResultEvent.text` and the token footer, and removes the cancel keyboard from the log message
- [x] 4.4 `tests/test_telegram_ui.py`: long log (> 4096 chars) triggers tail-trim with a `> …` marker and still only one log message
- [x] 4.5 `tests/test_telegram_ui.py`: > 4 lines in the log produces expandable-blockquote wrapping
- [x] 4.6 `tests/test_telegram_ui.py`: when MarkdownV2 edit raises, the renderer retries once with plain text and does not crash
- [x] 4.7 `tests/test_telegram_ui.py`: "at most two messages" invariant — count `send_message` calls end-to-end for a mixed stream (thinking + tool + text + final), assert exactly 2
- [x] 4.8 `tests/test_config.py` (or similar): `Settings.streaming_mode` default is `"thread"` and still accepts the legacy values

## 5. Docs & deploy

- [x] 5.1 Add a one-line note to `CLAUDE.md` (project) under "Run" or architecture listing the default `streaming_mode=thread`
- [x] 5.2 Run `uv run pytest tests/ -v` locally and ensure green
- [x] 5.3 Run `./deploy.sh` to push to the VPS (project convention: auto-deploy after task)
