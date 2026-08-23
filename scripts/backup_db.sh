#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="${DSAPP_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="$PROJECT_DIR/.env"

BACKUP_ROOT="$PROJECT_DIR/backups"
DAILY_DIR="$BACKUP_ROOT/daily"
WEEKLY_DIR="$BACKUP_ROOT/weekly"
MONTHLY_DIR="$BACKUP_ROOT/monthly"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env not found at $ENV_FILE"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

mkdir -p "$DAILY_DIR" "$WEEKLY_DIR" "$MONTHLY_DIR"

chmod 700 "$BACKUP_ROOT"

STAMP="$(date '+%Y-%m-%d_%H%M%S')"

DAILY_FILE="$DAILY_DIR/dsapp-$STAMP.dump"

cd "$PROJECT_DIR"

echo "Creating PostgreSQL backup..."

docker compose exec -T db \
    pg_dump \
    -Fc \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    > "$DAILY_FILE"

if [[ ! -s "$DAILY_FILE" ]]; then
    echo "ERROR: Backup file is empty."
    rm -f "$DAILY_FILE"
    exit 1
fi

echo "Verifying backup..."

docker compose exec -T db \
    pg_restore --list \
    < "$DAILY_FILE" \
    > /dev/null

chmod 600 "$DAILY_FILE"

echo "Backup verified: $DAILY_FILE"

#
# Sunday = weekly backup
#
if [[ "$(date '+%u')" == "7" ]]; then

    WEEKLY_FILE="$WEEKLY_DIR/dsapp-weekly-$STAMP.dump"

    cp "$DAILY_FILE" "$WEEKLY_FILE"
    chmod 600 "$WEEKLY_FILE"

    echo "Weekly backup created."

fi

#
# First day of month = monthly backup
#
if [[ "$(date '+%d')" == "01" ]]; then

    MONTHLY_FILE="$MONTHLY_DIR/dsapp-monthly-$STAMP.dump"

    cp "$DAILY_FILE" "$MONTHLY_FILE"
    chmod 600 "$MONTHLY_FILE"

    echo "Monthly backup created."

fi


prune_directory() {

    directory="$1"
    keep="$2"

    find "$directory" \
        -maxdepth 1 \
        -type f \
        -name '*.dump' \
        -printf '%T@ %p\n' \
        | sort -nr \
        | tail -n +"$((keep + 1))" \
        | cut -d' ' -f2- \
        | while IFS= read -r file
        do
            [[ -n "$file" ]] && rm -f "$file"
        done
}


#
# Retention
#
prune_directory "$DAILY_DIR" 7
prune_directory "$WEEKLY_DIR" 4
prune_directory "$MONTHLY_DIR" 12

echo "Backup complete."
