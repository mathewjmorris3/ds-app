#!/usr/bin/env bash
# Local persistence drill: dumps live DB, restores ONLY to a new temp DB, then drops
# only that DB. Dump persists with 0600 permissions; it does not protect the VM/disk.
set -Eeuo pipefail
umask 077
pg_admin(){ runuser -u postgres -- env -u PGHOST -u PGPORT -u PGUSER -u PGPASSWORD -u PGDATABASE "$@"; }
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
ENV_FILE="${DSAPP_ENV_FILE:-/etc/dsapp/app.env}"
ROOT="${DSAPP_DRILL_ROOT:-/var/backups/dsapp/restore-drills}"
[[ -r "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }
[[ "$(df -Pk / | awk 'NR==2{print $4}')" -ge 524288 ]] || { echo 'Less than 512 MiB free; refusing drill.' >&2; exit 1; }
set +x; set -a; . "$ENV_FILE"; set +a
POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"; POSTGRES_PORT="${POSTGRES_PORT:-5432}"
[[ "$POSTGRES_HOST" == 127.0.0.1 || "$POSTGRES_HOST" == localhost ]] || { echo 'Configured DB is not local.' >&2; exit 1; }
export PGPASSWORD="$POSTGRES_PASSWORD" PGHOST="$POSTGRES_HOST" PGPORT="$POSTGRES_PORT" PGUSER="$POSTGRES_USER"
psql --dbname="$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -Atqc 'SELECT 1' >/dev/null
install -d -o root -g root -m 0700 "$ROOT"
db_bytes="$(psql --dbname="$POSTGRES_DB" -Atqc 'SELECT pg_database_size(current_database())')"
free_bytes="$(df -B1 --output=avail "$ROOT" | tail -n 1 | tr -d ' ')"
(( free_bytes >= db_bytes * 2 + 134217728 )) || { echo 'Insufficient free space for dump and restored database.' >&2; exit 1; }
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
test_db="dsapp_restore_drill_${stamp,,}"
dump="$ROOT/${stamp}.dump"
tmp_dump="$ROOT/.${stamp}.partial"
if pg_admin psql --dbname=postgres -Atqc "SELECT 1 FROM pg_database WHERE datname='$test_db'" | grep -q 1; then echo "Refusing pre-existing drill DB $test_db" >&2; exit 1; fi
pg_admin createdb --maintenance-db=postgres --owner="$POSTGRES_USER" "$test_db"
cleanup(){ pg_admin dropdb --if-exists --maintenance-db=postgres "$test_db" >/dev/null 2>&1 || true; rm -f "$tmp_dump"; }
trap cleanup EXIT
printf 'Writing private local dump: %s\n' "$dump"
pg_dump --no-password --dbname="$POSTGRES_DB" --format=custom --file="$tmp_dump"
chmod 0600 "$tmp_dump"
pg_restore --list "$tmp_dump" >/dev/null
# The dump and parent directory are root-only. Root opens it and passes the
# already-open descriptor as stdin, so the postgres OS account can restore
# without making the archive readable or traversable on disk.
pg_admin pg_restore --dbname="$test_db" --role="$POSTGRES_USER" --no-owner --no-privileges --single-transaction --exit-on-error < "$tmp_dump"
query="SELECT (SELECT count(*) FROM core_dailysales)||':'||(SELECT count(*) FROM core_employeeearning)||':'||(SELECT count(*) FROM core_activitylog)"
live="$(psql --dbname="$POSTGRES_DB" -Atqc "$query")"
restored="$(psql --dbname="$test_db" -Atqc "$query")"
[[ "$live" == "$restored" ]] || { echo "Restore counts differ (live=$live restored=$restored). Drill archive was not published." >&2; exit 1; }
mv "$tmp_dump" "$dump"
printf 'Restore verified. Matched core row counts: %s. Temporary DB will be removed; local archive retained at %s.\n' "$live" "$dump"
printf '%s\n' 'This local archive does not protect against loss of this VM or its disk.'
