#!/bin/bash
# =============================================================
#  Cloud Quiz — EC2 Deployment Script
#  Ubuntu 22.04 LTS (Amazon Linux 2 also works with minor tweaks)
#
#  USAGE (run as ubuntu user, not root):
#    chmod +x deploy.sh
#    ./deploy.sh
#
#  What this script does:
#    1. Updates the system
#    2. Installs Python 3.11, PostgreSQL 15, Nginx
#    3. Creates the PostgreSQL database and user
#    4. Creates a Python virtualenv and installs dependencies
#    5. Runs Alembic migrations
#    6. Seeds the database with demo data
#    7. Configures Nginx as a reverse proxy
#    8. Installs and starts the Gunicorn systemd service
# =============================================================

set -euo pipefail   # exit on any error

# ── CONFIG — edit these before running ───────────────────────────────────────
APP_DIR="/home/ubuntu/cloud_quiz"
DB_NAME="cloudquiz"
DB_USER="cloudquiz"
DB_PASS="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"  # auto-generated
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"  # auto-generated
EC2_PUBLIC_IP="$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo '0.0.0.0')"

echo "============================================================"
echo "  Cloud Quiz EC2 Deployment"
echo "  App dir  : $APP_DIR"
echo "  Public IP: $EC2_PUBLIC_IP"
echo "============================================================"

# ── 1. System update ──────────────────────────────────────────────────────────
echo ""
echo ">>> [1/8] Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq

# ── 2. Install dependencies ───────────────────────────────────────────────────
echo ""
echo ">>> [2/8] Installing Python 3.11, PostgreSQL 15, Nginx..."
sudo apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    postgresql postgresql-contrib libpq-dev \
    nginx \
    git curl unzip \
    build-essential

# ── 3. PostgreSQL setup ───────────────────────────────────────────────────────
echo ""
echo ">>> [3/8] Configuring PostgreSQL..."
sudo systemctl start postgresql
sudo systemctl enable postgresql

sudo -u postgres psql <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = '${DB_USER}') THEN
        CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';
    END IF;
END
\$\$;

SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')
\gexec

GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

echo "    PostgreSQL: database '${DB_NAME}' ready."

# ── 4. Copy application files ─────────────────────────────────────────────────
echo ""
echo ">>> [4/8] Setting up application directory..."
sudo mkdir -p "$APP_DIR"
sudo chown ubuntu:ubuntu "$APP_DIR"

# If deploying from the zip (CI/CD), unzip here.
# For manual deploy: scp -r ./cloud_quiz_production ubuntu@EC2_IP:~/cloud_quiz
# The script assumes files are already in $APP_DIR.

# Create log directory
sudo mkdir -p /var/log/cloudquiz
sudo chown ubuntu:ubuntu /var/log/cloudquiz

# ── 5. Python virtual environment ────────────────────────────────────────────
echo ""
echo ">>> [5/8] Creating Python virtualenv and installing requirements..."
python3.11 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" -q
echo "    Python packages installed."

# ── 6. Write .env file ───────────────────────────────────────────────────────
echo ""
echo ">>> [6/8] Writing .env..."
cat > "$APP_DIR/backend/.env" <<ENV
APP_NAME="Cloud Quiz"
APP_VERSION="1.0.0"
DEBUG=false
ENVIRONMENT=production

DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

SECRET_KEY=${SECRET_KEY}
ACCESS_TOKEN_EXPIRE_MINUTES=1440

FRONTEND_ORIGINS=["http://${EC2_PUBLIC_IP}","http://localhost"]
EC2_PUBLIC_IP=${EC2_PUBLIC_IP}
ENV

chmod 600 "$APP_DIR/backend/.env"
echo "    .env written (permissions: 600)."

# ── 7. Alembic migrations + seed ─────────────────────────────────────────────
echo ""
echo ">>> [7/8] Running database migrations..."
cd "$APP_DIR/backend"
"$APP_DIR/venv/bin/alembic" -c "$APP_DIR/alembic.ini" upgrade head
echo "    Migrations applied."

echo "    Seeding demo data..."
"$APP_DIR/venv/bin/python" -m app.seed && echo "    Seed complete." || echo "    Seed skipped (already seeded)."

# ── 8. Nginx setup ────────────────────────────────────────────────────────────
echo ""
echo ">>> [8/8] Configuring Nginx..."
sudo cp "$APP_DIR/nginx/cloudquiz.conf" /etc/nginx/sites-available/cloudquiz
# Replace placeholder IP
sudo sed -i "s/YOUR_EC2_PUBLIC_IP/${EC2_PUBLIC_IP}/g" /etc/nginx/sites-available/cloudquiz
sudo ln -sf /etc/nginx/sites-available/cloudquiz /etc/nginx/sites-enabled/cloudquiz
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx && sudo systemctl enable nginx
echo "    Nginx configured and restarted."

# ── 9. Systemd service ────────────────────────────────────────────────────────
echo ""
echo ">>> Configuring systemd service..."
sudo cp "$APP_DIR/scripts/cloudquiz.service" /etc/systemd/system/cloudquiz.service
sudo systemctl daemon-reload
sudo systemctl enable cloudquiz
sudo systemctl restart cloudquiz
sleep 2
sudo systemctl status cloudquiz --no-pager

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  ✅  Deployment complete!"
echo ""
echo "  Application URL : http://${EC2_PUBLIC_IP}"
echo "  Health check    : http://${EC2_PUBLIC_IP}/health"
echo ""
echo "  Demo accounts:"
echo "    Admin   → admin@projexi.com   / admin1234"
echo "    Teacher → piyush@example.com  / piyush1234"
echo "    Student → alice@example.com   / student123"
echo ""
echo "  Generated secrets saved to: $APP_DIR/backend/.env"
echo "  DB password : ${DB_PASS}"
echo "  SECRET_KEY  : ${SECRET_KEY}"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status  cloudquiz"
echo "    sudo systemctl restart cloudquiz"
echo "    sudo journalctl -u cloudquiz -f"
echo "    sudo tail -f /var/log/nginx/cloudquiz_error.log"
echo "============================================================"
