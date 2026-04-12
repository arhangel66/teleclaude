## Why

The bot is working locally but needs to run 24/7 on a VPS (`root@64.176.73.226`) so that Telegram users can reach it anytime. We also need a simple, repeatable way to push future changes from the local dev machine to the server.

## What Changes

- Deploy the bot to `/opt/telegram-bridge` on `root@64.176.73.226`
- Install Python 3.12+ and `uv` on the server, sync dependencies
- Install `claude` CLI on the server (required for the subprocess bridge) and authenticate it
- Install a systemd unit (`telegram-bridge.service`) that runs the bot on boot and restarts on crash
- `.env` lives only on the server (never synced) — template shipped as `.env.example`
- Add `deploy.sh` to the repo root — one-command deploy: rsync code, `uv sync`, restart service, tail logs
- Verify the bot is alive by sending a test message from Telegram

## Capabilities

### New Capabilities

- `deployment`: Remote server setup, rsync-based code sync, systemd service management, one-command redeploy

### Modified Capabilities

(none)

## Impact

- New files: `deploy.sh`, `deploy/telegram-bridge.service`, `.env.example` (if not yet present), `.gitignore` updates
- New directory structure on server: `/opt/telegram-bridge/` with code, `.venv`, `files/`, `sessions.db`
- Requires SSH key access to `root@64.176.73.226` (assumed already configured)
- Requires `claude` CLI authentication on the server
