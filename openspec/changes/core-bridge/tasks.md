## 1. Project Setup

- [x] 1.1 Init project: pyproject.toml, uv add aiogram aiosqlite pydantic-settings
- [x] 1.2 Create .env.example with all required variables
- [x] 1.3 Create src/bot/config.py — Settings class (pydantic-settings, loads .env)

## 2. Core Services

- [x] 2.1 Create src/bot/services/session_store.py — SessionStore class (aiosqlite: get/set/reset session_id by chat_id, auto-create table)
- [x] 2.2 Create src/bot/services/claude_runner.py — ClaudeRunner class (spawn subprocess, parse NDJSON stream line-by-line, yield typed events, 10min timeout, one-per-user guard)
- [x] 2.3 Create src/bot/services/telegram_ui.py — TelegramUI class (send progress message, throttled edits every 2s, send final message with context size footer, split long messages)

## 3. Bot Wiring

- [x] 3.1 Create src/bot/construct.py — instantiate all services with DI
- [x] 3.2 Create src/bot/handlers.py — message handler (auth check, call runner, pipe events to UI) + /new and /start commands
- [x] 3.3 Create src/bot/main.py — entry point: build bot, register handlers, start polling

## 4. Testing & Smoke

- [x] 4.1 Manual smoke test: send text message, verify progress + final response + context size
- [x] 4.2 Test /new resets session
- [x] 4.3 Test unauthorized user is ignored
