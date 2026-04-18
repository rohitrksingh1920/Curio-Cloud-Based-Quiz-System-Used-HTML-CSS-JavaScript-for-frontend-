




set -euo pipefail

# ─────────────────────────────────────────────────────────────
#  CONFIGURATION  — edit SMTP before first run
# ─────────────────────────────────────────────────────────────
readonly APP_DIR="/home/ubuntu/curio"
readonly APP_USER="ubuntu"
readonly SERVICE_NAME="curio"
readonly DB_NAME="curio_db"
readonly DB_USER="curio_user"
readonly LOG_DIR="/var/log/curio"
readonly NGINX_CONF="/etc/nginx/sites-available/curio"

# SMTP — your Gmail App Password (no spaces in the 16-char code)
readonly SMTP_USER="rohitrk.singh1920@gmail.com"
readonly SMTP_PASS="cdjnzlsyvpirxcko"
readonly SMTP_FROM_NAME="Curio"

# ─────────────────────────────────────────────────────────────
#  COLOR HELPERS
# ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}>>> $*${NC}"; }
success() { echo -e "${GREEN}✅  $*${NC}"; }
warn()    { echo -e "${YELLOW}⚠️   $*${NC}"; }
error()   { echo -e "${RED}❌  $*${NC}" >&2; }
step()    { echo -e "\n${BOLD}[${1}/${TOTAL_STEPS}] ${2}${NC}"; }

TOTAL_STEPS=11
DEPLOY_LOG="/tmp/curio_deploy_$(date +%Y%m%d_%H%M%S).log"

# ─────────────────────────────────────────────────────────────
#  ERROR TRAP — logs the failing line and exits cleanly
# ─────────────────────────────────────────────────────────────
on_error() {
    local exit_code=$?
    local line_no=$1
    error "Deployment FAILED at line ${line_no} (exit code: ${exit_code})"
    error "Full log saved to: ${DEPLOY_LOG}"
    echo ""
    echo "──────────── Last 20 log lines ────────────"
    tail -20 "${DEPLOY_LOG}" 2>/dev/null || true
    echo "────────────────────────────────────────────"
    echo ""
    echo "To retry after fixing the error:"
    echo "  ./deploy.sh"
    exit "${exit_code}"
}
trap 'on_error ${LINENO}' ERR

# Redirect all output to both terminal and log file
exec > >(tee -a "${DEPLOY_LOG}") 2>&1

echo ""
echo -e "${BOLD}============================================================${NC}"
echo -e "${BOLD}  Curio Cloud Quiz — EC2 Deployment${NC}"
echo -e "${BOLD}  $(date)${NC}"
echo -e "${BOLD}============================================================${NC}"

# ─────────────────────────────────────────────────────────────
#  [1] PRE-FLIGHT VALIDATION
# ─────────────────────────────────────────────────────────────
step 1 "Pre-flight validation"

# Must not run as root
if [[ $EUID -eq 0 ]]; then
    error "Do not run this script as root. Run as the 'ubuntu' user."
    exit 1
fi
success "Running as user: $(whoami)"

# Check OS
if ! grep -q "Ubuntu 22" /etc/os-release 2>/dev/null; then
    warn "Not Ubuntu 22.04 — continuing anyway, but untested on this OS."
else
    success "OS: Ubuntu 22.04 LTS"
fi

# Validate required project files exist
REQUIRED_FILES=(
    "$APP_DIR/backend/requirements.txt"
    "$APP_DIR/backend/app/main.py"
    "$APP_DIR/alembic.ini"
    "$APP_DIR/frontend/index.html"
    "$APP_DIR/nginx/cloudquiz-ec2.conf"
    "$APP_DIR/scripts/cloudquiz.service"
)
for f in "${REQUIRED_FILES[@]}"; do
    if [[ ! -f "$f" ]]; then
        error "Required file missing: $f"
        error "Make sure you uploaded the full project to $APP_DIR"
        exit 1
    fi
done
success "All required project files present"

# Fetch EC2 public IP (with timeout so it doesn't hang on non-EC2)
EC2_PUBLIC_IP=$(curl -s --max-time 5 \
    http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "")
if [[ -z "$EC2_PUBLIC_IP" ]]; then
    warn "Could not auto-detect EC2 public IP — using 0.0.0.0"
    EC2_PUBLIC_IP="0.0.0.0"
fi
success "EC2 Public IP: $EC2_PUBLIC_IP"

# ─────────────────────────────────────────────────────────────
#  [2] SYSTEM PACKAGES
# ─────────────────────────────────────────────────────────────
step 2 "Installing system packages"

sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    postgresql-15 postgresql-client-15 libpq-dev \
    nginx \
    git curl unzip wget \
    build-essential \
    2>&1 | grep -v "^Get\|^Hit\|^Reading\|^Building\|^Calculating"

success "System packages installed"

# ─────────────────────────────────────────────────────────────
#  [3] POSTGRESQL
# ─────────────────────────────────────────────────────────────
step 3 "Configuring PostgreSQL"

sudo systemctl start postgresql
sudo systemctl enable postgresql --quiet

# Generate or reuse DB password
DB_PASS_FILE="$APP_DIR/.db_pass"
if [[ -f "$DB_PASS_FILE" ]]; then
    DB_PASS=$(cat "$DB_PASS_FILE")
    warn "Reusing existing DB password from $DB_PASS_FILE"
else
    DB_PASS=$(python3 -c 'import secrets; print(secrets.token_hex(20))')
    echo "$DB_PASS" > "$DB_PASS_FILE"
    chmod 600 "$DB_PASS_FILE"
fi

# Idempotent: create user/db only if they don't already exist
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = '${DB_USER}') THEN
        CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';
        RAISE NOTICE 'Created DB user: ${DB_USER}';
    ELSE
        ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASS}';
        RAISE NOTICE 'Updated DB user password: ${DB_USER}';
    END IF;
END \$\$;

SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')
\gexec

GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

# Verify connection
if PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" \
        -c "SELECT 1" -q &>/dev/null; then
    success "PostgreSQL: database '$DB_NAME' verified"
else
    error "Cannot connect to PostgreSQL as $DB_USER — check pg_hba.conf"
    exit 1
fi

# ─────────────────────────────────────────────────────────────
#  [4] DIRECTORIES
# ─────────────────────────────────────────────────────────────
step 4 "Creating directories"

sudo mkdir -p "$LOG_DIR"
sudo chown "$APP_USER:$APP_USER" "$LOG_DIR"
mkdir -p "$APP_DIR/static/avatars"
mkdir -p "$APP_DIR/backups"
chmod 755 "$APP_DIR/static" "$APP_DIR/static/avatars"
success "Directories created: $LOG_DIR, static/avatars, backups"

# ─────────────────────────────────────────────────────────────
#  [5] PYTHON VIRTUALENV
# ─────────────────────────────────────────────────────────────
step 5 "Python virtualenv + packages"

VENV="$APP_DIR/venv"
if [[ ! -d "$VENV" ]]; then
    python3.11 -m venv "$VENV"
    success "Created new virtualenv at $VENV"
fi

"$VENV/bin/pip" install --upgrade pip setuptools wheel -q

# Install with verbose error output so failed packages are visible
if ! "$VENV/bin/pip" install -r "$APP_DIR/backend/requirements.txt" \
        --no-warn-script-location 2>&1; then
    error "pip install failed — check requirements.txt"
    exit 1
fi
success "Python packages installed: $("$VENV/bin/pip" list --format=columns | wc -l) packages"

# ─────────────────────────────────────────────────────────────
#  [6] ENVIRONMENT FILE
# ─────────────────────────────────────────────────────────────
step 6 "Writing backend/.env"

ENV_FILE="$APP_DIR/backend/.env"

if [[ -f "$ENV_FILE" ]]; then
    warn ".env already exists — backing up to .env.bak and regenerating"
    cp "$ENV_FILE" "${ENV_FILE}.bak"
fi

# Generate fresh JWT secret key
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

cat > "$ENV_FILE" <<ENV
# ── Curio Cloud Quiz — Production .env ────────────────────────────────────
# Auto-generated by deploy.sh on $(date)
# Permissions: 600 (owner read-only)

# ── Application ─────────────────────────────────────────────────────────────
APP_NAME=Curio
APP_VERSION=1.0.0
DEBUG=False
ENVIRONMENT=production

# ── PostgreSQL ───────────────────────────────────────────────────────────────
DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

# ── JWT ──────────────────────────────────────────────────────────────────────
SECRET_KEY=${SECRET_KEY}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# ── CORS ─────────────────────────────────────────────────────────────────────
FRONTEND_ORIGINS=["http://${EC2_PUBLIC_IP}","http://localhost","http://127.0.0.1"]

# ── SMTP (Gmail App Password — no spaces in 16-char code) ───────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=${SMTP_USER}
SMTP_PASS=${SMTP_PASS}
EMAILS_FROM_NAME=${SMTP_FROM_NAME}

# ── AWS ──────────────────────────────────────────────────────────────────────
EC2_PUBLIC_IP=${EC2_PUBLIC_IP}
ALLOWED_HOSTS=["*"]
ENV

chmod 600 "$ENV_FILE"
success ".env written with 600 permissions"

# ─────────────────────────────────────────────────────────────
#  [7] ALEMBIC MIGRATIONS
# ─────────────────────────────────────────────────────────────
step 7 "Database migrations (Alembic)"

cd "$APP_DIR"
export PYTHONPATH="$APP_DIR"

# Validate alembic can connect before running
if ! "$VENV/bin/alembic" -c "$APP_DIR/alembic.ini" current 2>&1; then
    error "Alembic cannot read migration history — check DATABASE_URL in .env"
    exit 1
fi

"$VENV/bin/alembic" -c "$APP_DIR/alembic.ini" upgrade head
success "Migrations applied (includes quiz_enrollments RBAC table)"

# ─────────────────────────────────────────────────────────────
#  [8] SEED DATA
# ─────────────────────────────────────────────────────────────
step 8 "Seeding demo data"

cd "$APP_DIR"
SEED_RESULT=$("$VENV/bin/python" -m backend.app.seed 2>&1) || true
if echo "$SEED_RESULT" | grep -q "already seeded\|Skipping"; then
    warn "Database already seeded — skipping"
elif echo "$SEED_RESULT" | grep -q "complete\|✅"; then
    success "Demo data seeded"
else
    warn "Seed output: $SEED_RESULT"
fi

# ─────────────────────────────────────────────────────────────
#  [9] NGINX
# ─────────────────────────────────────────────────────────────
step 9 "Configuring Nginx"

# Copy and substitute EC2 IP in config
sudo cp "$APP_DIR/nginx/cloudquiz-ec2.conf" "$NGINX_CONF"
sudo sed -i "s/YOUR_EC2_PUBLIC_IP/${EC2_PUBLIC_IP}/g" "$NGINX_CONF"

# Enable site and disable default
sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/curio
sudo rm -f /etc/nginx/sites-enabled/default

# Test config before applying
if ! sudo nginx -t 2>&1; then
    error "Nginx config test FAILED — reverting"
    sudo rm -f /etc/nginx/sites-enabled/curio
    exit 1
fi

sudo systemctl enable nginx --quiet
sudo systemctl restart nginx
success "Nginx configured and running"

# ─────────────────────────────────────────────────────────────
#  [10] SYSTEMD SERVICE
# ─────────────────────────────────────────────────────────────
step 10 "Systemd service"

sudo cp "$APP_DIR/scripts/cloudquiz.service" \
    "/etc/systemd/system/${SERVICE_NAME}.service"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}" --quiet
sudo systemctl restart "${SERVICE_NAME}"

# Wait up to 15 seconds for service to be active
for i in $(seq 1 15); do
    if sudo systemctl is-active --quiet "${SERVICE_NAME}"; then
        break
    fi
    sleep 1
done

if ! sudo systemctl is-active --quiet "${SERVICE_NAME}"; then
    error "Service failed to start. Showing journal:"
    sudo journalctl -u "${SERVICE_NAME}" -n 30 --no-pager
    exit 1
fi
success "Service '${SERVICE_NAME}' is active"

# ─────────────────────────────────────────────────────────────
#  [11] SMOKE TEST
# ─────────────────────────────────────────────────────────────
step 11 "Smoke test"

sleep 2  # Let Gunicorn finish binding

HEALTH_URL="http://127.0.0.1/health"
HEALTH_RESPONSE=$(curl -s --max-time 10 "$HEALTH_URL" 2>&1 || echo "FAILED")

if echo "$HEALTH_RESPONSE" | grep -q '"status"'; then
    success "Health check passed: $HEALTH_RESPONSE"
else
    warn "Health check at $HEALTH_URL returned: $HEALTH_RESPONSE"
    warn "The app may still be starting up — check: sudo journalctl -u ${SERVICE_NAME} -f"
fi

# ─────────────────────────────────────────────────────────────
#  DONE
# ─────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}============================================================${NC}"
echo -e "${GREEN}${BOLD}  ✅  Deployment complete!  $(date)${NC}"
echo -e "${GREEN}${BOLD}============================================================${NC}"
echo ""
echo -e "  ${BOLD}Application URL${NC}  : http://${EC2_PUBLIC_IP}"
echo -e "  ${BOLD}Health check${NC}     : http://${EC2_PUBLIC_IP}/health"
echo -e "  ${BOLD}API docs (dev)${NC}   : http://${EC2_PUBLIC_IP}/docs  (DEBUG=True only)"
echo ""
echo -e "  ${BOLD}Demo accounts:${NC}"
echo    "    Teacher → rohitrk.singh1920@gmail.com / rohit1234"
echo    "    Student → alice@example.com            / student123"
echo    "    Admin   → admin@projexi.com             / admin1234"
echo ""
echo -e "  ${BOLD}Credentials saved to${NC}: $APP_DIR/backend/.env"
echo -e "  ${BOLD}Deploy log${NC}          : $DEPLOY_LOG"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo    "    sudo systemctl status  curio"
echo    "    sudo systemctl restart curio"
echo    "    sudo journalctl -u curio -f          # live app logs"
echo    "    sudo tail -f /var/log/curio/error.log"
echo    "    sudo tail -f /var/log/nginx/cloudquiz_error.log"
echo    "    ./scripts/update.sh                  # deploy new code"
echo    "    ./scripts/backup.sh                  # manual DB backup"
echo ""
