## Why

Currently in `verbose` streaming mode every thinking step, tool call, and intermediate text arrives as its own Telegram message, which spams the chat. In `compact` mode the progress message is deleted right before the final answer is sent, so the user loses visibility into what Claude actually did. We want a middle ground: **one** persistent message that captures all the thinking/tool-use log (compact, as a blockquote so it stays collapsed) plus **one** message with the final answer — at most two messages per interaction.

## What Changes

- Add a new streaming mode (`thread`) that produces at most two messages per prompt:
  1. A single "log" message, edited in place, containing all intermediate thinking + tool-use lines formatted as a Telegram MarkdownV2 blockquote (`>` prefix / `expandable blockquote`) so it stays visually compact.
  2. A separate final-answer message sent after Claude finishes.
- The log message keeps the Cancel inline button until the final answer is sent; then the button is removed but the message is **preserved** (not deleted as in current `compact` mode).
- Intermediate assistant text emissions (`on_text`) are appended to the log blockquote rather than being promoted to the final-answer position.
- Make `thread` the default value of `settings.streaming_mode`; keep `verbose`/`compact`/`quiet` available for backwards compatibility.
- Apply MarkdownV2 escaping when rendering the blockquote so arbitrary tool arguments and thinking snippets don't break Telegram parsing. Fall back to plain text if MarkdownV2 send/edit fails.
- Handle Telegram's 4096-char per-message limit: if the log overflows, keep the most recent lines and prepend a `…` truncation marker; do not spawn additional log messages.

## Capabilities

### New Capabilities
- `thread-streaming`: Two-message interaction pattern — a single edited-in-place progress/thinking log (blockquote) plus one final-answer message.

### Modified Capabilities
<!-- No existing capability specs on disk to modify; verbose/compact/quiet behavior is preserved as alternate modes. -->

## Impact

- **Code**: `src/bot/services/telegram_ui.py` (new `ThreadRenderer`, blockquote builder, MarkdownV2 escape helper, extended `TelegramUI` edit that accepts `parse_mode`), `src/bot/services/task_runner.py` (no change expected — renderer contract stays), `src/bot/config.py` (add `thread` to `streaming_mode` literal, change default).
- **Tests**: `tests/test_telegram_ui.py` (append-to-log semantics, truncation behavior, blockquote formatting, MarkdownV2 escape, final-answer as second message).
- **Dependencies**: None new — uses existing `aiogram.Bot.edit_message_text` with `parse_mode="MarkdownV2"`.
- **Config**: `.env.example` mention of the new default.
