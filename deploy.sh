#!/usr/bin/env bash
# TeleClaude deploy script.
# Usage:
#   ./deploy.sh             — rsync code, uv sync, restart service, tail logs
#   ./deploy.sh --bootstrap — one-time server setup
#   ./deploy.sh --logs      — tail journald logs
#   ./deploy.sh --status    — show systemd status

set -euo pipefail

SERVER="root@64.176.73.226"
REMOTE_DIR="/opt/telegram-bridge"
SERVICE="telegram-bridge"
UNIT_SRC="deploy/telegram-bridge.service"
UNIT_DST="/etc/systemd/system/telegram-bridge.service"

RSYNC_EXCLUDES=(
    --exclude=".venv/"
    --exclude="__pycache__/"
    --exclude="*.pyc"
    --exclude="sessions.db"
    --exclude="files/"
    --exclude="workspace/"
    --exclude=".env"
    --exclude=".git/"
    --exclude="untracked/"
    --exclude="openspec/"
    --exclude=".idea/"
    --exclude="*.egg-info/"
)

log()  { printf "\033[1;34m[deploy]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[deploy]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31m[deploy]\033[0m %s\n" "$*" >&2; exit 1; }

cmd_logs() {
    ssh -t "$SERVER" "journalctl -fu $SERVICE -n 200"
}

cmd_status() {
    ssh "$SERVER" "systemctl status $SERVICE --no-pager"
}

ensure_env_on_server() {
    if ! ssh "$SERVER" "test -f $REMOTE_DIR/.env"; then
        die ".env is missing on the server ($REMOTE_DIR/.env). Run ./deploy.sh --bootstrap and create it from .env.example."
    fi
}

rsync_code() {
    log "Syncing code -> $SERVER:$REMOTE_DIR"
    rsync -az --delete "${RSYNC_EXCLUDES[@]}" ./ "$SERVER:$REMOTE_DIR/"
    ssh "$SERVER" "chown -R claude:claude $REMOTE_DIR"
}

remote_uv_sync() {
    log "Running uv sync on server"
    ssh "$SERVER" "cd $REMOTE_DIR && /root/.local/bin/uv sync --frozen"
}

restart_service() {
    log "Restarting $SERVICE"
    ssh "$SERVER" "systemctl restart $SERVICE"
}

cmd_deploy() {
    ensure_env_on_server
    rsync_code
    remote_uv_sync
    restart_service
    log "Deploy done. Tailing logs (Ctrl-C to exit)..."
    cmd_logs
}

cmd_bootstrap() {
    log "Bootstrapping $SERVER"

    ssh "$SERVER" "mkdir -p $REMOTE_DIR $REMOTE_DIR/workspace $REMOTE_DIR/files"

    if ! ssh "$SERVER" "command -v /root/.local/bin/uv >/dev/null 2>&1"; then
        log "Installing uv"
        ssh "$SERVER" "curl -LsSf https://astral.sh/uv/install.sh | sh"
    else
        log "uv already installed"
    fi

    if ! ssh "$SERVER" "command -v claude >/dev/null 2>&1"; then
        warn "claude CLI not found on server. Install it and authenticate:"
        warn "  ssh $SERVER"
        warn "  # follow claude.ai/code install instructions, then: claude"
        die "Bootstrap aborted — install claude CLI first."
    else
        log "claude CLI present: $(ssh "$SERVER" 'claude --version 2>/dev/null || echo unknown')"
    fi

    rsync_code
    remote_uv_sync

    log "Installing systemd unit"
    scp "$UNIT_SRC" "$SERVER:$UNIT_DST"
    ssh "$SERVER" "systemctl daemon-reload && systemctl enable $SERVICE"

    if ! ssh "$SERVER" "test -f $REMOTE_DIR/.env"; then
        warn ".env is missing on the server."
        warn "Create it manually:"
        warn "  scp .env.example $SERVER:$REMOTE_DIR/.env   # then edit on the server"
        warn "  ssh $SERVER 'nano $REMOTE_DIR/.env'"
        warn "After creating .env: ssh $SERVER 'systemctl start $SERVICE'"
    else
        log ".env already present. Starting service."
        ssh "$SERVER" "systemctl start $SERVICE"
    fi

    log "Bootstrap done."
}

case "${1:-}" in
    --bootstrap) cmd_bootstrap ;;
    --logs)      cmd_logs ;;
    --status)    cmd_status ;;
    "")          cmd_deploy ;;
    *)           die "Unknown option: $1" ;;
esac
