# #!/bin/bash
# # =============================================================
# #  Cloud Quiz — PostgreSQL Backup Script
# #
# #  USAGE (manual):
# #    chmod +x backup.sh
# #    ./backup.sh
# #
# #  CRON (daily at 2 AM):
# #    0 2 * * * /home/ubuntu/cloud_quiz/scripts/backup.sh >> /var/log/cloudquiz/backup.log 2>&1
# # =============================================================

# set -euo pipefail

# APP_DIR="/home/ubuntu/cloud_quiz"
# BACKUP_DIR="$APP_DIR/backups"
# TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
# BACKUP_FILE="$BACKUP_DIR/cloudquiz_${TIMESTAMP}.sql.gz"

# # Load DB credentials from .env
# source <(grep -E '^DATABASE_URL=' "$APP_DIR/backend/.env" | sed 's/DATABASE_URL=/export DATABASE_URL=/')

# # Parse DATABASE_URL: postgresql://USER:PASS@HOST:PORT/DBNAME
# DB_USER=$(echo "$DATABASE_URL" | sed -E 's|postgresql://([^:]+):.*|\1|')
# DB_PASS=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^:]+:([^@]+)@.*|\1|')
# DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^@]+@([^:/]+).*|\1|')
# DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^@]+@[^:]+:([0-9]+)/.*|\1|')
# DB_NAME=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^/]+/(.+)|\1|')

# mkdir -p "$BACKUP_DIR"

# echo "[$(date)] Starting backup → $BACKUP_FILE"

# PGPASSWORD="$DB_PASS" pg_dump \
#     -h "$DB_HOST" \
#     -p "$DB_PORT" \
#     -U "$DB_USER" \
#     -d "$DB_NAME" \
#     --format=plain \
#     --no-owner \
#     --no-privileges \
#     | gzip > "$BACKUP_FILE"

# SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
# echo "[$(date)] Backup complete. Size: $SIZE"

# # ── Retention: keep last 7 days ──────────────────────────────
# find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete
# echo "[$(date)] Old backups cleaned up."











#!/bin/bash
# =============================================================
#  Curio Cloud Quiz — PostgreSQL Backup Script
#
#  MANUAL RUN:
#    chmod +x backup.sh
#    ./backup.sh
#
#  AUTOMATED (daily at 2 AM via cron):
#    crontab -e
#    0 2 * * * /home/ubuntu/curio/scripts/backup.sh >> /var/log/curio/backup.log 2>&1
# =============================================================

set -euo pipefail

APP_DIR="/home/ubuntu/curio"
BACKUP_DIR="$APP_DIR/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/curio_${TIMESTAMP}.sql.gz"

# Load DATABASE_URL from .env
source <(grep -E '^DATABASE_URL=' "$APP_DIR/backend/.env" | \
         sed 's/DATABASE_URL=/export DATABASE_URL=/')

# Parse DATABASE_URL: postgresql://USER:PASS@HOST:PORT/DBNAME
DB_USER=$(echo "$DATABASE_URL" | sed -E 's|postgresql://([^:]+):.*|\1|')
DB_PASS=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^:]+:([^@]+)@.*|\1|')
DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^@]+@([^:/]+).*|\1|')
DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^@]+@[^:]+:([0-9]+)/.*|\1|')
DB_NAME=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^/]+/(.+)|\1|')

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup → $BACKUP_FILE"

PGPASSWORD="$DB_PASS" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --format=plain \
    --no-owner \
    --no-privileges \
    | gzip > "$BACKUP_FILE"

SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "[$(date)] Backup complete. File: $BACKUP_FILE  Size: $SIZE"

# Keep last 7 days only
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete
echo "[$(date)] Old backups cleaned up. Done."
