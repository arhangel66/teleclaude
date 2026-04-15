## 1. Deploy Artifacts in Repo

- [x] 1.1 Create `deploy/telegram-bridge.service` — systemd unit (Type=simple, WorkingDirectory=/opt/telegram-bridge, ExecStart=.venv/bin/python -m src.bot.main, Restart=always, RestartSec=5, EnvironmentFile=/opt/telegram-bridge/.env, WantedBy=multi-user.target)
- [x] 1.2 Create `.env.example` at repo root with all required variables and comments
- [x] 1.3 Update `.gitignore` to ensure `.env`, `sessions.db`, `files/` are ignored
- [x] 1.4 Create `deploy.sh` at repo root — modes: default (deploy), `--bootstrap`, `--logs`, `--status`; uses rsync with excludes, runs uv sync, restarts service, tails journalctl

## 2. One-time Server Bootstrap

- [x] 2.1 Run `./deploy.sh --bootstrap` — creates `/opt/telegram-bridge/` and `/opt/telegram-bridge/workspace/`, rsyncs code, writes systemd unit, `systemctl daemon-reload`, `systemctl enable telegram-bridge`
- [x] 2.2 Create `/opt/telegram-bridge/.env` on server (TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS, WORKING_DIRECTORY=/opt/telegram-bridge/workspace, SQLITE_DB=/opt/telegram-bridge/sessions.db, CLAUDE_BINARY=/usr/bin/claude)
- [x] 2.3 Verify claude auth on server — `/usr/bin/claude` v2.1.100 ok
- [x] 2.4 `systemctl start telegram-bridge` — active (running), polling начался

## 3. Smoke Test

- [x] 3.1 Tail logs: `./deploy.sh --logs`
- [ ] 3.2 Send a test Telegram message from allowed chat_id; observe progress + final response
- [ ] 3.3 Send `/new`, verify session reset
- [ ] 3.4 Send a photo, verify file saved under `/opt/telegram-bridge/files/{chat_id}/` and Claude sees the path
- [ ] 3.5 Start a long Claude task and press Cancel; verify subprocess killed in logs

## 4. Validate Redeploy Flow

- [x] 4.1 Trivial code change (deploy.sh: added `workspace/` to rsync excludes; systemd unit: User=claude)
- [x] 4.2 Run `./deploy.sh` — rsync delta ok, uv sync noop, service restarted
- [x] 4.3 `sessions.db` is in rsync excludes — preserved on server
