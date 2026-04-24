



set -euo pipefail

# ─────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────
readonly APP_DIR="/home/ubuntu/curio"
readonly SERVICE_NAME="curio"
readonly VENV="$APP_DIR/venv"
readonly ENV_FILE="$APP_DIR/backend/.env"

# ─────────────────────────────────────────────────────────────
#  COLOR HELPERS
# ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}>>> $*${NC}"; }
success() { echo -e "${GREEN}  $*${NC}"; }
warn()    { echo -e "${YELLOW}   $*${NC}"; }
error()   { echo -e "${RED}  $*${NC}" >&2; }

UPDATE_LOG="/tmp/curio_update_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "${UPDATE_LOG}") 2>&1

on_error() {
    local exit_code=$?
    local line_no=$1
    error "Update FAILED at line ${line_no} (exit code: ${exit_code})"
    error "Log: ${UPDATE_LOG}"
    echo ""
    warn "Rolling back: restarting last known-good service..."
    sudo systemctl restart "${SERVICE_NAME}" 2>/dev/null || true
    echo ""
    echo "Diagnose with:"
    echo "  sudo journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
    echo "  tail -50 ${UPDATE_LOG}"
    exit "${exit_code}"
}
trap 'on_error ${LINENO}' ERR

TOTAL_STEPS=8

echo ""
echo -e "${BOLD}============================================================${NC}"
echo -e "${BOLD}  Curio Cloud Quiz — Update   $(date)${NC}"
echo -e "${BOLD}============================================================${NC}"

# ─────────────────────────────────────────────────────────────
#  [1] PRE-FLIGHT
# ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[1/${TOTAL_STEPS}] Pre-flight validation${NC}"

[[ $EUID -eq 0 ]] && { error "Do not run as root"; exit 1; }

[[ -d "$VENV" ]] || { error "Virtualenv not found at $VENV — run deploy.sh first"; exit 1; }

[[ -f "$ENV_FILE" ]] || { error ".env not found at $ENV_FILE — run deploy.sh first"; exit 1; }

# Test DB connection using credentials from .env
DB_URL=$(grep '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)
if [[ -z "$DB_URL" ]]; then
    error "DATABASE_URL not found in $ENV_FILE"
    exit 1
fi
success "Pre-flight checks passed"

# ─────────────────────────────────────────────────────────────
#  [2] GIT PULL
# ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[2/${TOTAL_STEPS}] Pulling latest code${NC}"

if [[ -d "$APP_DIR/.git" ]]; then
    cd "$APP_DIR"
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    info "Branch: $CURRENT_BRANCH"

    # Stash any local changes to avoid conflicts
    if ! git diff --quiet 2>/dev/null; then
        warn "Local changes detected — stashing"
        git stash push -m "auto-stash before update $(date)"
    fi

    BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "")
    git pull origin "$CURRENT_BRANCH" --ff-only 2>&1 || {
        warn "Fast-forward failed — trying merge pull"
        git pull origin "$CURRENT_BRANCH" 2>&1
    }
    AFTER=$(git rev-parse HEAD 2>/dev/null || echo "")

    if [[ "$BEFORE" == "$AFTER" ]]; then
        warn "No new commits — continuing with current code"
    else
        COMMIT_COUNT=$(git rev-list --count "${BEFORE}..${AFTER}" 2>/dev/null || echo "?")
        success "Pulled ${COMMIT_COUNT} new commit(s)"
        git log --oneline "${BEFORE}..${AFTER}" 2>/dev/null | head -5 || true
    fi
else
    warn "Not a git repo — skipping pull (using files as-is in $APP_DIR)"
fi

# ─────────────────────────────────────────────────────────────
#  [3] PIP INSTALL
# ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[3/${TOTAL_STEPS}] Updating Python dependencies${NC}"

REQS="$APP_DIR/backend/requirements.txt"
[[ -f "$REQS" ]] || { error "requirements.txt not found: $REQS"; exit 1; }

"$VENV/bin/pip" install --upgrade pip setuptools wheel -q

if ! "$VENV/bin/pip" install -r "$REQS" --no-warn-script-location -q 2>&1; then
    error "pip install failed — check $REQS for invalid package specs"
    exit 1
fi
success "Dependencies up-to-date"

# ─────────────────────────────────────────────────────────────
#  [4] ALEMBIC MIGRATIONS
# ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[4/${TOTAL_STEPS}] Running database migrations${NC}"

cd "$APP_DIR"
export PYTHONPATH="$APP_DIR"

ALEMBIC_INI="$APP_DIR/alembic.ini"
[[ -f "$ALEMBIC_INI" ]] || { error "alembic.ini not found: $ALEMBIC_INI"; exit 1; }

# Show current migration state
CURRENT=$("$VENV/bin/alembic" -c "$ALEMBIC_INI" current 2>&1 || echo "unknown")
info "Current migration: $CURRENT"

if ! "$VENV/bin/alembic" -c "$ALEMBIC_INI" upgrade head 2>&1; then
    error "Alembic migration failed"
    error "Check DB connection and that all models are importable:"
    error "  cd $APP_DIR && PYTHONPATH=$APP_DIR $VENV/bin/python -c 'from backend.app.models.quiz import QuizEnrollment'"
    exit 1
fi
success "Migrations applied"

# ─────────────────────────────────────────────────────────────
#  [5] STATIC DIRS
# ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[5/${TOTAL_STEPS}] Ensuring static directories${NC}"

mkdir -p "$APP_DIR/static/avatars"
chmod 755 "$APP_DIR/static" "$APP_DIR/static/avatars"
success "static/avatars directory ready"

# ─────────────────────────────────────────────────────────────
#  [6] RELOAD GUNICORN
# ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[6/${TOTAL_STEPS}] Reloading Gunicorn (zero-downtime)${NC}"

if sudo systemctl is-active --quiet "${SERVICE_NAME}"; then
    sudo systemctl reload "${SERVICE_NAME}" 2>/dev/null || \
        sudo systemctl restart "${SERVICE_NAME}"
    sleep 2

    if ! sudo systemctl is-active --quiet "${SERVICE_NAME}"; then
        error "Service failed after reload — checking logs"
        sudo journalctl -u "${SERVICE_NAME}" -n 30 --no-pager
        exit 1
    fi
    success "Gunicorn reloaded gracefully"
else
    warn "Service not running — starting it"
    sudo systemctl start "${SERVICE_NAME}"
    sleep 3
    sudo systemctl is-active --quiet "${SERVICE_NAME}" || {
        error "Service failed to start"
        sudo journalctl -u "${SERVICE_NAME}" -n 30 --no-pager
        exit 1
    }
    success "Service started"
fi

# ─────────────────────────────────────────────────────────────
#  [7] NGINX RELOAD
# ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[7/${TOTAL_STEPS}] Nginx config reload${NC}"

if sudo nginx -t 2>&1; then
    sudo systemctl reload nginx
    success "Nginx reloaded"
else
    error "Nginx config test failed — NOT reloading (current config still active)"
    exit 1
fi

# ─────────────────────────────────────────────────────────────
#  [8] SMOKE TEST
# ─────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[8/${TOTAL_STEPS}] Smoke test${NC}"

sleep 1
HEALTH=$(curl -s --max-time 8 "http://127.0.0.1/health" 2>&1 || echo "TIMEOUT")

if echo "$HEALTH" | grep -q '"status"'; then
    success "Health check passed: $HEALTH"
else
    warn "Health check returned: $HEALTH"
    warn "App may still be warming up — check: sudo journalctl -u ${SERVICE_NAME} -f"
fi

EC2_IP=$(grep '^EC2_PUBLIC_IP=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 || echo "")

echo ""
echo -e "${GREEN}${BOLD}============================================================${NC}"
echo -e "${GREEN}${BOLD}    Update complete!  $(date)${NC}"
echo -e "${GREEN}${BOLD}============================================================${NC}"
[[ -n "$EC2_IP" ]] && echo "  App: http://${EC2_IP}"
echo "  Log: ${UPDATE_LOG}"
echo ""
