## Why

When a user sends a message, Claude takes time to process it. During this time the Telegram chat shows no activity indicator, so the user doesn't know if the bot received the message. Telegram's "typing" chat action solves this — it shows "typing..." under the bot's name while processing is in progress.

## What Changes

- Send `typing` chat action immediately when a new message is received, before Claude starts processing.
- Keep the `typing` action alive by re-sending it periodically (every ~4 seconds) while Claude is working, since Telegram auto-expires the status after 5 seconds.
- Stop the typing indicator once the first progress message or final result is sent.

## Capabilities

### New Capabilities
- `typing-indicator`: Periodic "typing" chat action broadcast during Claude processing.

### Modified Capabilities
<!-- No existing specs to modify -->

## Impact

- **Code**: `src/bot/handlers.py` (trigger typing on message), `src/bot/services/telegram_ui.py` (typing action logic).
- **Dependencies**: None new — `aiogram.Bot.send_chat_action` is already available.
- **APIs**: Uses Telegram Bot API `sendChatAction` with `action=typing`.
