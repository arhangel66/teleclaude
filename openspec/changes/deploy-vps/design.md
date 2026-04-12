## Context

Local project layout: `src/bot/`, `pyproject.toml`, `uv.lock`, `sessions.db`, `files/`, `tests/`. The bot is an async Python 3.12+ app using aiogram 3 long-polling. Per PRD, deployment target is "systemd on VPS, logging via journald".

Server `root@64.176.73.226` (Ubuntu 24.04, Python 3.12.3, x86_64) inspected — already has:
- `uv` installed at `/root/.local/bin/uv`
- `claude` CLI 2.1.100 authenticated (history/cache present in `~/.claude/`)
- Several services under `/opt/` with systemd units using the pattern `ExecStart=/opt/<service>/.venv/bin/<tool>`, `Restart=always`, `EnvironmentFile=/opt/<service>/.env`, `WantedBy=multi-user.target`
- No existing `telegram-bridge` directory or service
- Disk ~85% full (42G/52G) — tight but workable

This simplifies bootstrap: only need to create dir, rsync code, `uv sync`, install our systemd unit, and `.env`.

## Goals / Non-Goals

**Goals:**
- One-time server bootstrap (install uv, claude, create dir, systemd unit)
- `deploy.sh` for subsequent code pushes from dev machine
- Bot auto-restarts on crash and on reboot
- Logs accessible via `journalctl`
- Smoke test after deploy — send Telegram message and verify response

**Non-Goals:**
- CI/CD pipeline (GitHub Actions etc.) — manual `./deploy.sh` is enough for now
- Zero-downtime deploys — restart is acceptable (users rarely notice)
- Container/Docker packaging — systemd + rsync is simpler
- Multi-server / HA — single VPS

## Decisions

### D1: Install path `/opt/telegram-bridge`

`/opt/` is the standard FHS location for third-party services. Clean separation from `/root`, survives user switches.

### D2: rsync over SSH for code sync

rsync is idempotent, fast (delta transfers), excludes patterns trivially. Alternative: `git pull` — requires the server to have git credentials and a clone; more moving parts. rsync with `--delete` gives us a clean sync from our working tree.

**Excluded from rsync:** `.venv/`, `__pycache__/`, `sessions.db`, `files/`, `.env`, `.git/`, `untracked/`, `*.pyc`, `openspec/`.

### D3: `uv sync` on server, not local `.venv` shipped

Ship only `pyproject.toml` + `uv.lock`, run `uv sync` remotely. Keeps the deploy package small and avoids architecture mismatch (local macOS arm64 → Linux x86_64).

### D4: systemd user-mode vs system-mode → **system-mode as root**

Server runs as root (per user's SSH target). Simplest: `/etc/systemd/system/telegram-bridge.service`, `User=root`, `WorkingDirectory=/opt/telegram-bridge`, `ExecStart=/opt/telegram-bridge/.venv/bin/python -m bot.main`.

### D5: `.env` stays on server only

Never sync `.env` — it contains bot token and chat IDs. Bootstrap creates `.env` from `.env.example` interactively if missing.

### D6: Claude CLI on server

`claude` is already installed and authenticated on the server (`/usr/bin/claude`, `~/.claude/` populated). Bootstrap just verifies this and skips if present.

### D7: Working directory for Claude subprocess

The PRD says Claude runs in a "fixed working directory". On the server, set `WORKING_DIRECTORY=/opt/telegram-bridge/workspace` (a dedicated empty dir for Claude to roam in). This keeps Claude's `Write`/`Bash` operations away from bot source code.

### D8: deploy.sh UX

- `./deploy.sh` — full deploy: rsync → `uv sync` → `systemctl restart` → `journalctl -fu` (tail logs, Ctrl-C to exit)
- `./deploy.sh --bootstrap` — one-time server setup (install uv, claude, create dirs, systemd unit, prompt for .env)
- `./deploy.sh --logs` — just tail logs
- `./deploy.sh --status` — service status

## Risks / Trade-offs

- **Claude CLI not authenticated** → `deploy.sh --bootstrap` checks and instructs user to run `ssh root@… claude` interactively
- **Server rebooted and bot crashed silently** → `Restart=always` in systemd unit
- **`.env` lost on server** → deploy script detects missing `.env` and aborts with clear message
- **sessions.db wiped by accident** → rsync excludes it, only initial bootstrap creates an empty one
- **Port/firewall** → no inbound ports needed (long-polling, outbound only). Nothing to configure.
