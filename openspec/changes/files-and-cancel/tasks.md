## 1. File Handling

- [x] 1.1 Add file download logic to handlers.py — handle photo, voice, video, document content types, save to files/{chat_id}/
- [x] 1.2 Format prompt with file path and caption, pass to claude_runner

## 2. Cancel Operation

- [x] 2.1 Add cancel method to ClaudeRunner — SIGTERM by chat_id
- [x] 2.2 Add inline "Cancel" button to progress message in TelegramUI
- [x] 2.3 Add callback query handler for cancel button in handlers.py
- [x] 2.4 Remove cancel button on subprocess completion

## 3. Testing

- [x] 3.1 Smoke test: send photo, verify Claude receives the file path
- [x] 3.2 Smoke test: press Cancel during long operation, verify subprocess killed
