#!/usr/bin/env bash
# TeleClaude deploy script with gated pipeline.
#
# Usage:
#   ./deploy.sh                    — full gated deploy (ruff → pytest → review → rsync → uv sync → restart → verify)
#   ./deploy.sh --skip-review      — skip claude-review gate only
#   ./deploy.sh --skip-tests       — skip pytest + claude-review gates
#   ./deploy.sh --bootstrap        — one-time server setup
#   ./deploy.sh --logs             — tail journald logs
#   ./deploy.sh --status           — show systemd status

set -euo pipefail

SERVER="root@64.176.73.226"
REMOTE_DIR="/opt/telegram-bridge"
SERVICE="telegram-bridge"
UNIT_SRC="deploy/telegram-bridge.service"
UNIT_DST="/etc/systemd/system/telegram-bridge.service"
DEPLOY_LOG="./deploy.log"
REVIEW_MODEL="claude-haiku-4-5-20251001"
VERIFY_RETRIES=2
VERIFY_SLEEP=5
POLLING_MARKER="Bot started polling"

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
    --exclude="deploy.log"
    --exclude=".omc/"
)

SKIP_REVIEW=0
SKIP_TESTS=0
MODE=""

log()  { printf "\033[1;34m[deploy]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[deploy]\033[0m %s\n" "$*" >&2; }
die()  { printf "\033[1;31m[deploy]\033[0m %s\n" "$*" >&2; exit 1; }

log_step() {
    local name="$1" duration="$2" status="$3"
    printf "[%s] STEP=%s DURATION=%s STATUS=%s\n" \
        "$(date -u +%FT%TZ)" "$name" "$duration" "$status" >> "$DEPLOY_LOG"
}

run_step() {
    local name="$1"; shift
    local start end duration rc
    start=$(date +%s)
    set +e
    "$@"
    rc=$?
    set -e
    end=$(date +%s)
    duration=$((end - start))
    if (( rc == 0 )); then
        log_step "$name" "$duration" "ok"
    else
        log_step "$name" "$duration" "fail"
        die "Step '$name' failed (exit=$rc)"
    fi
}

cmd_logs() {
    ssh -t "$SERVER" "journalctl -fu $SERVICE -n 200"
}

cmd_status() {
    ssh "$SERVER" "systemctl status $SERVICE --no-pager"
}

ensure_env_on_server() {
    if ! ssh "$SERVER" "test -f $REMOTE_DIR/.env"; then
        die ".env is missing on the server ($REMOTE_DIR/.env). Run ./deploy.sh --bootstrap first."
    fi
}

run_ruff() {
    log "Ruff: uv run ruff check src/ tests/"
    uv run ruff check src/ tests/
}

run_pytest() {
    log "Pytest: uv run pytest tests/ -v"
    uv run pytest tests/ -v
}

run_claude_review() {
    log "Claude review (model=$REVIEW_MODEL) on diff vs origin/main"
    local diff
    if ! diff=$(git diff origin/main...HEAD -- '*.py' '*.sh' 2>/dev/null); then
        warn "git diff failed (origin/main missing?) — skipping review"
        return 0
    fi
    if [[ -z "$diff" ]]; then
        log "Empty diff vs origin/main — skipping review"
        return 0
    fi

    local prompt
    prompt=$(cat <<'EOF'
You are a code review gate for a Telegram bot (Python / aiogram).
Output EXACTLY one JSON object on its own line, nothing else, no prose, no markdown fences:
{"verdict":"pass"|"fail","severity":"critical"|"high"|"low"|"none","reason":"<short>"}

Block (verdict=fail, severity=critical or high) ONLY on:
  - exposed secrets / API keys / tokens hardcoded in source
  - RCE / shell injection / unsafe subprocess
  - SQL injection
  - path traversal
  - data loss bugs
  - deadlocks / broken async
  - chat_id leaks to unauthorized users

Style / perf / minor issues → verdict=pass, severity=low.
NEVER fail on test coverage, lint, or formatting — those have their own gates.

Diff follows:
EOF
)

    local full_input
    full_input="${prompt}"$'\n'"${diff}"

    local envelope
    if ! envelope=$(
        printf '%s' "$full_input" | claude -p --output-format json --max-turns 1 --model "$REVIEW_MODEL" 2>&1
    ); then
        warn "claude CLI invocation failed:"
        warn "$envelope"
        die "Claude review invocation failed"
    fi

    local parsed
    parsed=$(python3 - "$envelope" <<'PY'
import json, re, sys
envelope_raw = sys.argv[1]
try:
    env = json.loads(envelope_raw)
except Exception:
    env = {}
content = env.get("result") or env.get("content") or ""
if isinstance(content, list):
    content = " ".join(str(x) for x in content)
m = re.search(r"\{[^{}]*\"verdict\"[^{}]*\}", str(content), flags=re.S)
if not m:
    print(json.dumps({"verdict": "fail", "severity": "critical",
                      "reason": "review output did not include a verdict JSON"}))
    sys.exit(0)
try:
    obj = json.loads(m.group(0))
except Exception as e:
    print(json.dumps({"verdict": "fail", "severity": "critical",
                      "reason": f"invalid review JSON: {e}"}))
    sys.exit(0)
print(json.dumps({
    "verdict": obj.get("verdict", "fail"),
    "severity": obj.get("severity", "none"),
    "reason": obj.get("reason", ""),
}))
PY
)

    local verdict severity reason
    verdict=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["verdict"])' "$parsed")
    severity=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["severity"])' "$parsed")
    reason=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["reason"])' "$parsed")

    log "Review verdict=$verdict severity=$severity reason=$reason"

    if [[ "$verdict" == "fail" ]] && { [[ "$severity" == "critical" ]] || [[ "$severity" == "high" ]]; }; then
        die "Claude review blocked ($severity): $reason"
    fi
}

git_push() {
    log "Pushing to origin"
    git push
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

verify_deploy() {
    log "Verify: systemctl is-active + '$POLLING_MARKER' in journal"
    local attempt=1
    while (( attempt <= VERIFY_RETRIES )); do
        if ssh "$SERVER" "systemctl is-active --quiet $SERVICE \
            && journalctl -u $SERVICE --since '60 seconds ago' --no-pager \
               | grep -q '$POLLING_MARKER'"; then
            log "Service active and polling marker present."
            return 0
        fi
        if (( attempt < VERIFY_RETRIES )); then
            warn "Verify attempt $attempt failed — sleeping ${VERIFY_SLEEP}s and retrying"
            sleep "$VERIFY_SLEEP"
        fi
        ((attempt++))
    done
    warn "Last 50 journal lines for $SERVICE:"
    ssh "$SERVER" "journalctl -u $SERVICE --no-pager -n 50" >&2 || true
    return 1
}

cmd_deploy() {
    : > "$DEPLOY_LOG"
    log_step "start" 0 "ok"

    ensure_env_on_server

    run_step git_push git_push

    if (( SKIP_TESTS == 0 )); then
        run_step ruff   run_ruff
        run_step pytest run_pytest
        if (( SKIP_REVIEW == 0 )); then
            run_step claude_review run_claude_review
        else
            log "Skipping claude-review (flag)"
        fi
    else
        log "Skipping ruff, pytest and claude-review (flag)"
    fi

    run_step rsync   rsync_code
    run_step uv_sync remote_uv_sync
    run_step restart restart_service
    run_step verify  verify_deploy
    log_step "done" 0 "ok"
    log "Deploy done. Tail logs with ./deploy.sh --logs"
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

while (( $# > 0 )); do
    case "$1" in
        --skip-review) SKIP_REVIEW=1 ;;
        --skip-tests)  SKIP_TESTS=1; SKIP_REVIEW=1 ;;
        --bootstrap|--logs|--status)
            [[ -n "$MODE" ]] && die "Conflicting modes: $MODE and $1"
            MODE="$1" ;;
        -h|--help)
            sed -n '2,9p' "$0"
            exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
    shift
done

case "$MODE" in
    --bootstrap) cmd_bootstrap ;;
    --logs)      cmd_logs ;;
    --status)    cmd_status ;;
    "")          cmd_deploy ;;
esac
