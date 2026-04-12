## 1. Typing indicator in TelegramUI

- [x] 1.1 Add `start_typing(chat_id)` method to `TelegramUI` that starts a background task sending `typing` action every 4 seconds
- [x] 1.2 Add `stop_typing(chat_id)` method to `TelegramUI` that cancels the background task

## 2. Integrate into message handler

- [x] 2.1 Call `start_typing` in `on_message` handler before starting Claude processing
- [x] 2.2 Call `stop_typing` in `finally` block to ensure cleanup on both success and error

## 3. Testing

- [x] 3.1 Write test for typing loop sending action at correct interval
- [x] 3.2 Write test for stop_typing cancelling the background task
- [x] 3.3 Write test for cleanup on handler error
