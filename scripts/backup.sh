

set -euo pipefail

# ─────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────
readonly APP_DIR="/home/ubuntu/curio"
readonly BACKUP_DIR="$APP_DIR/backups"
readonly ENV_FILE="$APP_DIR/backend/.env"
readonly RETAIN_DAYS=7          # delete backups older than this
readonly MIN_BACKUP_BYTES=500   # alert if backup is suspiciously small

# Optional S3 upload — set bucket name to enable:
readonly S3_BUCKET=""  # e.g. "my-curio-backups" — leave empty to skip

# ─────────────────────────────────────────────────────────────
#  COLOR HELPERS
# ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
success() { echo -e "${GREEN}✅  $*${NC}"; }
error()   { echo -e "${RED}❌  $*${NC}" >&2; }
warn()    { echo -e "${YELLOW}⚠️   $*${NC}"; }

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/curio_${TIMESTAMP}.sql.gz"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

on_error() {
    local exit_code=$?
    local line_no=$1
    error "$LOG_PREFIX Backup FAILED at line ${line_no} (exit code: ${exit_code})"
    # Remove incomplete backup file if it exists
    [[ -f "$BACKUP_FILE" ]] && rm -f "$BACKUP_FILE" && warn "Removed incomplete backup file"
    exit "${exit_code}"
}
trap 'on_error ${LINENO}' ERR

echo "$LOG_PREFIX ═══════════════════════════════════════"
echo "$LOG_PREFIX Curio Backup Starting"
echo "$LOG_PREFIX ═══════════════════════════════════════"

# ─────────────────────────────────────────────────────────────
#  VALIDATION
# ─────────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
    error "$LOG_PREFIX .env not found: $ENV_FILE"
    exit 1
fi

# Check pg_dump is available
if ! command -v pg_dump &>/dev/null; then
    error "$LOG_PREFIX pg_dump not found — install: sudo apt-get install postgresql-client"
    exit 1
fi

# ─────────────────────────────────────────────────────────────
#  PARSE DATABASE_URL
# ─────────────────────────────────────────────────────────────
DATABASE_URL=$(grep '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)

if [[ -z "$DATABASE_URL" ]]; then
    error "$LOG_PREFIX DATABASE_URL not set in $ENV_FILE"
    exit 1
fi

# Parse: postgresql://USER:PASS@HOST:PORT/DBNAME
DB_USER=$(echo "$DATABASE_URL" | sed -E 's|postgresql://([^:]+):.*|\1|')
DB_PASS=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^:]+:([^@]+)@.*|\1|')
DB_HOST=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^@]+@([^:/]+).*|\1|')
DB_PORT=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^@]+@[^:]+:([0-9]+)/.*|\1|' || echo "5432")
DB_NAME=$(echo "$DATABASE_URL" | sed -E 's|postgresql://[^/]+/(.+)|\1|')

# Validate all parts were parsed
for VAR in DB_USER DB_PASS DB_HOST DB_NAME; do
    if [[ -z "${!VAR}" ]]; then
        error "$LOG_PREFIX Failed to parse $VAR from DATABASE_URL"
        exit 1
    fi
done

# Test DB connectivity before attempting backup
if ! PGPASSWORD="$DB_PASS" pg_isready -h "$DB_HOST" -p "${DB_PORT:-5432}" \
        -U "$DB_USER" -d "$DB_NAME" -q; then
    error "$LOG_PREFIX Cannot connect to PostgreSQL at ${DB_HOST}:${DB_PORT:-5432}"
    error "$LOG_PREFIX Check that PostgreSQL is running: sudo systemctl status postgresql"
    exit 1
fi

echo "$LOG_PREFIX Database:  $DB_NAME on $DB_HOST:${DB_PORT:-5432}"

# ─────────────────────────────────────────────────────────────
#  CREATE BACKUP
# ─────────────────────────────────────────────────────────────
mkdir -p "$BACKUP_DIR"
echo "$LOG_PREFIX Creating backup → $BACKUP_FILE"

PGPASSWORD="$DB_PASS" pg_dump \
    -h "$DB_HOST" \
    -p "${DB_PORT:-5432}" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --format=plain \
    --no-owner \
    --no-privileges \
    --no-comments \
    | gzip > "$BACKUP_FILE"

# Validate backup is non-empty and not suspiciously small
BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || echo 0)
if [[ "$BACKUP_SIZE" -lt "$MIN_BACKUP_BYTES" ]]; then
    error "$LOG_PREFIX Backup file too small ($BACKUP_SIZE bytes) — possible empty dump"
    rm -f "$BACKUP_FILE"
    exit 1
fi

SIZE_HUMAN=$(du -sh "$BACKUP_FILE" | cut -f1)
success "$LOG_PREFIX Backup complete: $BACKUP_FILE ($SIZE_HUMAN)"

# ─────────────────────────────────────────────────────────────
#  OPTIONAL S3 UPLOAD
# ─────────────────────────────────────────────────────────────
if [[ -n "$S3_BUCKET" ]]; then
    if command -v aws &>/dev/null; then
        S3_KEY="backups/curio_${TIMESTAMP}.sql.gz"
        echo "$LOG_PREFIX Uploading to s3://${S3_BUCKET}/${S3_KEY}..."
        if aws s3 cp "$BACKUP_FILE" "s3://${S3_BUCKET}/${S3_KEY}" \
                --storage-class STANDARD_IA --quiet; then
            success "$LOG_PREFIX Uploaded to S3: s3://${S3_BUCKET}/${S3_KEY}"
        else
            warn "$LOG_PREFIX S3 upload failed — local backup retained"
        fi
    else
        warn "$LOG_PREFIX S3_BUCKET set but aws CLI not installed — skipping S3 upload"
    fi
fi

# ─────────────────────────────────────────────────────────────
#  RETENTION
# ─────────────────────────────────────────────────────────────
DELETED=$(find "$BACKUP_DIR" -name "*.sql.gz" -mtime "+${RETAIN_DAYS}" -print -delete | wc -l)
if [[ "$DELETED" -gt 0 ]]; then
    echo "$LOG_PREFIX Retention: deleted $DELETED backup(s) older than ${RETAIN_DAYS} days"
fi

# ─────────────────────────────────────────────────────────────
#  SUMMARY
# ─────────────────────────────────────────────────────────────
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "*.sql.gz" | wc -l)
OLDEST=$(find "$BACKUP_DIR" -name "*.sql.gz" -printf '%T+ %p\n' 2>/dev/null | \
    sort | head -1 | awk '{print $1}' || echo "n/a")

echo "$LOG_PREFIX ───────────────────────────────────────"
echo "$LOG_PREFIX Total backups stored : $BACKUP_COUNT"
echo "$LOG_PREFIX Oldest backup        : $OLDEST"
echo "$LOG_PREFIX Backup directory     : $BACKUP_DIR"
echo "$LOG_PREFIX ═══════════════════════════════════════"
echo "$LOG_PREFIX Backup complete."
echo "$LOG_PREFIX ═══════════════════════════════════════"
echo ""
echo "To restore this backup:"
echo "  gunzip < $BACKUP_FILE | \\"
echo "    PGPASSWORD='$DB_PASS' psql -h $DB_HOST -p ${DB_PORT:-5432} -U $DB_USER -d $DB_NAME"
