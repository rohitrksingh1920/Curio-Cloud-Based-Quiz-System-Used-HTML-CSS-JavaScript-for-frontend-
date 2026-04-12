#!/bin/bash
# =============================================================
#  Cloud Quiz — Update Script (zero-downtime re-deploy)
#  Run this whenever you push new code to EC2.
#
#  USAGE:
#    chmod +x update.sh
#    ./update.sh
# =============================================================

set -euo pipefail

APP_DIR="/home/ubuntu/cloud_quiz"

echo "============================================================"
echo "  Cloud Quiz — Updating application"
echo "============================================================"

# ── 1. Pull latest code (if using git) ───────────────────────
if [ -d "$APP_DIR/.git" ]; then
    echo ">>> Pulling latest code from git..."
    cd "$APP_DIR"
    git pull origin main
fi

# ── 2. Install / update Python packages ──────────────────────
echo ""
echo ">>> Updating Python dependencies..."
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" -q
echo "    Dependencies up-to-date."

# ── 3. Run any new Alembic migrations ────────────────────────
echo ""
echo ">>> Running database migrations..."
cd "$APP_DIR/backend"
"$APP_DIR/venv/bin/alembic" -c "$APP_DIR/alembic.ini" upgrade head
echo "    Migrations applied."

# ── 4. Reload Gunicorn (zero-downtime) ───────────────────────
echo ""
echo ">>> Reloading Gunicorn (graceful restart)..."
sudo systemctl reload cloudquiz || sudo systemctl restart cloudquiz
sleep 2
sudo systemctl status cloudquiz --no-pager -l

# ── 5. Reload Nginx config if changed ────────────────────────
echo ""
echo ">>> Reloading Nginx..."
sudo nginx -t && sudo systemctl reload nginx
echo "    Nginx reloaded."

echo ""
echo "============================================================"
echo "  ✅  Update complete!"
echo "============================================================"
