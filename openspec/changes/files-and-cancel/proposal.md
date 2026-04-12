## Why

After Phase 1 (core bridge), the bot handles only text. Users need to send photos, documents, voice messages, and video to Claude for processing. Additionally, long-running Claude operations need a cancel mechanism to avoid waiting 10 minutes for a timeout.

## What Changes

- File handling: download photos, voice, video, documents from Telegram, save locally, pass paths to Claude
- Cancel button: inline "Cancel" on progress messages, sends SIGTERM to the Claude subprocess
- Skills support: any message starting with `/` is forwarded to Claude as-is (e.g. `/standup`)

## Capabilities

### New Capabilities

- `file-handling`: Download and store Telegram attachments, pass file paths to Claude in the prompt
- `cancel-operation`: Inline cancel button on progress messages, subprocess termination

### Modified Capabilities

- `claude-runner`: Add file path injection into prompts, expose subprocess handle for cancellation
- `telegram-ui`: Add inline cancel button to progress messages

## Impact

- Modified: claude_runner.py (file path in prompt, cancel support)
- Modified: telegram_ui.py (cancel inline button)
- Modified: handlers.py (file download logic, cancel callback)
- New directory: files/{chat_id}/ for stored attachments
