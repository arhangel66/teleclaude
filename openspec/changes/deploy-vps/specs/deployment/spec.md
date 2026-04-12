## ADDED Requirements

### Requirement: One-command deploy script
The repo SHALL contain `deploy.sh` at the repo root that, when run with no arguments, syncs code to the VPS, installs dependencies, restarts the service, and tails logs.

#### Scenario: Routine deploy
- **WHEN** the developer runs `./deploy.sh`
- **THEN** code is rsynced to `/opt/telegram-bridge` on the server, `uv sync` runs, `systemctl restart telegram-bridge` runs, and logs are tailed via `journalctl -fu telegram-bridge`

#### Scenario: Deploy aborts if .env missing on server
- **WHEN** `./deploy.sh` runs and `/opt/telegram-bridge/.env` does not exist on the server
- **THEN** the script aborts with a clear message instructing the user to run `./deploy.sh --bootstrap`

### Requirement: One-time bootstrap mode
The `deploy.sh` script SHALL support `--bootstrap` that prepares a clean server: installs `uv`, installs `claude` CLI, creates `/opt/telegram-bridge` directory tree, installs the systemd unit, enables it, and prompts for `.env` if missing.

#### Scenario: Bootstrap a fresh server
- **WHEN** the developer runs `./deploy.sh --bootstrap` against a clean server
- **THEN** uv, claude, service directory, and systemd unit are installed; the script prompts the user to create `.env` and authenticate `claude` CLI

#### Scenario: Bootstrap skips what exists
- **WHEN** `--bootstrap` runs and components already exist
- **THEN** existing components are left untouched; missing components are installed

### Requirement: systemd unit for auto-restart
A `deploy/telegram-bridge.service` unit file SHALL be present in the repo and installed to `/etc/systemd/system/` during bootstrap. The unit SHALL have `Restart=always`, `RestartSec=5`, `User=root`, `WorkingDirectory=/opt/telegram-bridge`, and run the bot via `.venv/bin/python -m bot.main`.

#### Scenario: Bot crashes
- **WHEN** the bot process crashes
- **THEN** systemd restarts it within 5 seconds

#### Scenario: Server reboots
- **WHEN** the server reboots
- **THEN** the bot starts automatically

### Requirement: Secrets never leave the server
The `deploy.sh` script SHALL NOT copy `.env` to or from the server. `.env` SHALL live only on the server.

#### Scenario: Local .env exists
- **WHEN** `./deploy.sh` runs with a local `.env` file present
- **THEN** the local `.env` is NOT transferred to the server

### Requirement: rsync excludes runtime artifacts
The `deploy.sh` script SHALL exclude these paths from rsync: `.venv/`, `__pycache__/`, `*.pyc`, `sessions.db`, `files/`, `.env`, `.git/`, `untracked/`, `openspec/`.

#### Scenario: Local sessions.db differs from server
- **WHEN** the local `sessions.db` has been modified during development
- **THEN** it is NOT copied to the server, preserving the server's real session data

### Requirement: Logs available via journalctl
After deploy, logs from the bot SHALL be accessible via `journalctl -u telegram-bridge`.

#### Scenario: Check recent logs
- **WHEN** the developer runs `./deploy.sh --logs`
- **THEN** the server tails recent journald output for the `telegram-bridge` unit

### Requirement: Smoke test after deploy
After a successful deploy, the developer SHALL manually verify bot health by sending a Telegram message and checking for a response within 10 seconds.

#### Scenario: Post-deploy verification
- **WHEN** deploy completes and logs are tailing
- **THEN** the developer sends a test Telegram message and observes the response and log events
