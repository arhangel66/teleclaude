## 1. Deploy Artifacts in Repo

- [ ] 1.1 Create `deploy/telegram-bridge.service` — systemd unit (Type=simple, WorkingDirectory=/opt/telegram-bridge, ExecStart=.venv/bin/python -m bot.main, Restart=always, RestartSec=5, EnvironmentFile=/opt/telegram-bridge/.env, WantedBy=multi-user.target)
- [ ] 1.2 Create `.env.example` at repo root with all required variables and comments
- [ ] 1.3 Update `.gitignore` to ensure `.env`, `sessions.db`, `files/` are ignored
- [ ] 1.4 Create `deploy.sh` at repo root — modes: default (deploy), `--bootstrap`, `--logs`, `--status`; uses rsync with excludes, runs uv sync, restarts service, tails journalctl

## 2. One-time Server Bootstrap

- [ ] 2.1 Run `./deploy.sh --bootstrap` — creates `/opt/telegram-bridge/` and `/opt/telegram-bridge/workspace/`, rsyncs code, writes systemd unit, `systemctl daemon-reload`, `systemctl enable telegram-bridge`
- [ ] 2.2 Create `/opt/telegram-bridge/.env` on server (manual, from template): fill TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS, WORKING_DIRECTORY=/opt/telegram-bridge/workspace, SQLITE_DB=/opt/telegram-bridge/sessions.db, FILES_DIR=/opt/telegram-bridge/files, CLAUDE_BINARY=/usr/bin/claude
- [ ] 2.3 Verify claude auth on server: `ssh root@64.176.73.226 claude --version` and confirm authentication works
- [ ] 2.4 `systemctl start telegram-bridge` and check `systemctl status`

## 3. Smoke Test

- [ ] 3.1 Tail logs: `./deploy.sh --logs`
- [ ] 3.2 Send a test Telegram message from allowed chat_id; observe progress + final response
- [ ] 3.3 Send `/new`, verify session reset
- [ ] 3.4 Send a photo, verify file saved under `/opt/telegram-bridge/files/{chat_id}/` and Claude sees the path
- [ ] 3.5 Start a long Claude task and press Cancel; verify subprocess killed in logs

## 4. Validate Redeploy Flow

- [ ] 4.1 Make a trivial code change locally (e.g. comment edit)
- [ ] 4.2 Run `./deploy.sh` — verify rsync delta, service restart, logs continue
- [ ] 4.3 Confirm `sessions.db` on server is preserved (not overwritten by local)
