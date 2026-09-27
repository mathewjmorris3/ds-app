#!/usr/bin/env bash
# Resume an existing installation safely; never creates/drops DBs or resets roles.
# Run from repo: sudo bash deploy/deploy_existing.sh
set -Eeuo pipefail
umask 077
REPO="${DSAPP_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
APP_ROOT="${DSAPP_APP_ROOT:-/opt/ds-app/source}"
VENV="${DSAPP_VENV:-/opt/ds-app/.venv}"
ENV_FILE="${DSAPP_ENV_FILE:-/etc/dsapp/app.env}"
UNIT_FILE="${DSAPP_UNIT_FILE:-/etc/systemd/system/dsapp.service}"
CADDY_FILE="${DSAPP_CADDY_FILE:-/etc/caddy/Caddyfile}"
BACKUP_ROOT="${DSAPP_CONFIG_BACKUPS:-/var/backups/dsapp/predeploy}"
LAN_IP="${DSAPP_LAN_IP:-192.168.0.41}"
LAN_CIDR="${DSAPP_LAN_CIDR:-192.168.0.0/24}"
LAN_HOSTNAME="${DSAPP_HOSTNAME:-}"
TEST_ENV="${DSAPP_TEST_ENV:-/etc/dsapp/test.env}"
fail(){ printf 'STOP: %s\n' "$*" >&2; exit 1; }
pg_admin(){ runuser -u postgres -- env -u PGHOST -u PGPORT -u PGUSER -u PGPASSWORD -u PGDATABASE "$@"; }
[[ $EUID -eq 0 ]] || fail 'Run with sudo.'
[[ -f "$REPO/app/manage.py" && -f "$REPO/app/requirements.txt" ]] || fail "Repository not found: $REPO"
[[ -f "$ENV_FILE" ]] || fail "Missing $ENV_FILE; run inspect_server.sh and configure credentials without replacing existing roles."
[[ -f "$CADDY_FILE" ]] || fail "Missing existing Caddyfile $CADDY_FILE; inspect before proceeding."
[[ -d "$APP_ROOT/app" && -x "$VENV/bin/python" ]] || fail 'Existing app tree or virtualenv is missing; inspect and repair its owner/path manually first.'
getent passwd dsapp >/dev/null || fail 'Dedicated dsapp service account is missing; no account was created.'
runuser -u dsapp -- test -r "$ENV_FILE" || fail 'Existing service account cannot read app.env; inspect ownership/mode.'
if ! command -v rsync >/dev/null; then apt-get update; apt-get install -y rsync; fi
[[ "$(df -Pk / | awk 'NR==2 {print $4}')" -ge 1048576 ]] || fail 'Less than 1 GiB free; stopping.'
ip -o -4 addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "$LAN_IP" || fail "LAN address $LAN_IP is not assigned. Set DSAPP_LAN_IP explicitly."

# Load only the root-managed application environment and verify the EXISTING DB
# login before taking a private, verified pre-migration backup.
set +x
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
: "${POSTGRES_DB:?POSTGRES_DB missing}" "${POSTGRES_USER:?POSTGRES_USER missing}" "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD missing}"
POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"; POSTGRES_PORT="${POSTGRES_PORT:-5432}"
[[ "$POSTGRES_HOST" == 127.0.0.1 || "$POSTGRES_HOST" == localhost || "$POSTGRES_HOST" == /var/run/postgresql ]] || fail 'Application database host is not local; inspect before deployment.'
export PGPASSWORD="$POSTGRES_PASSWORD" PGHOST="$POSTGRES_HOST" PGPORT="$POSTGRES_PORT" PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB"
psql -X -v ON_ERROR_STOP=1 -Atqc 'SELECT 1' >/dev/null || fail 'Configured application role cannot connect to configured database; no migrations run.'

# Never run tests against an existing database: Django's test runner writes to
# it. Generate fresh role and database names and leave all prior test resources
# untouched.
TEST_TOKEN="$(date -u +%Y%m%d%H%M%S)_$(openssl rand -hex 4)"
TEST_DB="dsapp_test_deploy_$TEST_TOKEN"
TEST_ROLE="dsapp_test_role_$TEST_TOKEN"
[[ "$POSTGRES_DB" != "$TEST_DB" ]] || fail 'Generated test DB conflicts with the live application DB.'
[[ "$TEST_ROLE" != "$POSTGRES_USER" ]] || fail 'Generated test role conflicts with the application role.'
[[ "$TEST_ENV" == /etc/dsapp/* ]] || fail 'DSAPP_TEST_ENV must be under /etc/dsapp so its permissions remain restricted.'
[[ -d "$(dirname "$TEST_ENV")" ]] || fail 'Directory for DSAPP_TEST_ENV does not exist; create and secure it before deployment.'
[[ -z "$LAN_HOSTNAME" || "$LAN_HOSTNAME" =~ ^[A-Za-z0-9.-]+$ ]] || fail 'DSAPP_HOSTNAME must be a plain DNS hostname.'
role_exists="$(pg_admin psql -X -Atqc "SELECT 1 FROM pg_roles WHERE rolname='$TEST_ROLE'")"
[[ -z "$role_exists" ]] || fail "Generated test role $TEST_ROLE already exists; retry after inspection."
test_db_exists="$(pg_admin psql -X -Atqc "SELECT 1 FROM pg_database WHERE datname='$TEST_DB'")"
[[ -z "$test_db_exists" ]] || fail "Generated test database $TEST_DB already exists; retry after inspection."
TEST_PASSWORD="$(openssl rand -hex 32)"

# Detect unexpected host configuration before creating even disposable test
# resources. A matching existing DS proxy and unit are safe to resume.
if ! { grep -qE '^:80[[:space:]]*\{' "$CADDY_FILE" && grep -qF '/usr/share/caddy' "$CADDY_FILE"; } && ! grep -qF '# Managed by dsapp deploy_existing.sh' "$CADDY_FILE"; then
  fail 'Caddyfile is neither the known package default nor expected DS proxy; inspect manually before proceeding.'
fi
fragment="$(systemctl show dsapp.service -p FragmentPath --value 2>/dev/null || true)"
if [[ -n "$fragment" && "$fragment" != "$UNIT_FILE" ]]; then
  fail "systemd loads dsapp.service from unexpected path $fragment; inspect it before proceeding."
fi
if [[ -f "$UNIT_FILE" ]] && ! { grep -qF '127.0.0.1:8000' "$UNIT_FILE" && grep -qF "WorkingDirectory=$APP_ROOT/app" "$UNIT_FILE" && grep -qF "EnvironmentFile=$ENV_FILE" "$UNIT_FILE" && grep -qF "$VENV/bin/gunicorn" "$UNIT_FILE"; }; then
  fail 'Existing app unit differs from repository paths/bind; inspect it before proceeding.'
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 0700 "$BACKUP_ROOT/$stamp"
SNAP="$BACKUP_ROOT/$stamp"
db_bytes="$(psql -X -Atqc 'SELECT pg_database_size(current_database())')"
free_bytes="$(df -B1 --output=avail "$SNAP" | tail -n 1 | tr -d ' ')"
(( free_bytes >= db_bytes * 2 + 268435456 )) || fail 'Insufficient free space for a verified database dump and deployment snapshot.'
printf 'Backing up current deployment config to %s\n' "$SNAP"
cp -a "$ENV_FILE" "$SNAP/app.env"
cp -a "$CADDY_FILE" "$SNAP/Caddyfile"
[[ ! -f "$UNIT_FILE" ]] || cp -a "$UNIT_FILE" "$SNAP/dsapp.service"
[[ ! -f "$TEST_ENV" ]] || cp -a "$TEST_ENV" "$SNAP/test.env"
[[ ! -f /etc/systemd/system/caddy.service ]] || cp -a /etc/systemd/system/caddy.service "$SNAP/caddy.service"
if [[ -d "$APP_ROOT" ]]; then tar -C "$(dirname "$APP_ROOT")" -czf "$SNAP/application-source.tar.gz" "$(basename "$APP_ROOT")"; fi
chmod -R go-rwx "$SNAP"
printf 'Creating and verifying pre-migration PostgreSQL dump...\n'
pg_dump --no-password --format=custom --file="$SNAP/database-before-migration.dump"
pg_restore --list "$SNAP/database-before-migration.dump" >/dev/null
chmod 0600 "$SNAP/database-before-migration.dump"
printf 'Pre-migration database backup verified.\n'

# Always make fresh uniquely named test resources. Existing test databases,
# roles, and test.env remain untouched except for a backed-up pointer update.
# The app role is never granted database creation privileges.
role_sql="$(mktemp /run/dsapp-test-role.XXXXXX)"
chown root:postgres "$role_sql"; chmod 0640 "$role_sql"
printf "CREATE ROLE %s LOGIN PASSWORD '%s';\n" "$TEST_ROLE" "$TEST_PASSWORD" > "$role_sql"
role_error="$(mktemp /run/dsapp-test-role-error.XXXXXX)"
chmod 0600 "$role_error"
if ! pg_admin psql -X -v ON_ERROR_STOP=1 -f "$role_sql" >/dev/null 2>"$role_error"; then
  safe_error="$(sed "s/$TEST_PASSWORD/[redacted]/g" "$role_error" | tail -n 6)"
  rm -f "$role_sql" "$role_error"
  fail "Could not create the uniquely named restricted test role; PostgreSQL reported: ${safe_error:-unknown error}. The app role/database was not changed."
fi
rm -f "$role_sql" "$role_error"
db_error="$(mktemp /run/dsapp-test-db-error.XXXXXX)"
chmod 0600 "$db_error"
if ! pg_admin createdb --owner="$TEST_ROLE" "$TEST_DB" 2>"$db_error"; then
  safe_error="$(tail -n 6 "$db_error")"
  rm -f "$db_error"
  fail "Could not create isolated test database as local PostgreSQL administrator; PostgreSQL reported: ${safe_error:-unknown error}. The app role/database was not changed."
fi
rm -f "$db_error"
test_env_tmp="$(mktemp "$(dirname "$TEST_ENV")/.test.env.XXXXXX")"
cat > "$test_env_tmp" <<ENV
DSAPP_TEST_DB=$TEST_DB
DSAPP_TEST_USER=$TEST_ROLE
DSAPP_TEST_PASSWORD=$TEST_PASSWORD
DSAPP_TEST_HOST=127.0.0.1
DSAPP_TEST_PORT=5432
ENV
chmod 0640 "$test_env_tmp"; chown root:dsapp "$test_env_tmp"
mv "$test_env_tmp" "$TEST_ENV"
unset TEST_PASSWORD

if systemctl is-active --quiet dsapp.service; then printf 'Stopping app briefly after verified backup...\n'; systemctl stop dsapp.service; fi
printf 'Installing Python dependencies in existing virtualenv...\n'
"$VENV/bin/python" -m pip install -r "$REPO/app/requirements.txt"
printf 'Updating application source (excluding local secrets, virtualenv, Git history, and backups)...\n'
rsync -a --exclude='.git/' --exclude='.env' --exclude='.venv/' --exclude='backups/' "$REPO/" "$APP_ROOT/"
chown -R root:dsapp "$APP_ROOT"
find "$APP_ROOT" -type d -exec chmod 0750 {} +
find "$APP_ROOT" -type f -exec chmod 0640 {} +
chmod 0750 "$APP_ROOT/app/manage.py"
# Ensure the systemd service identity can traverse the existing venv and read its installed packages.
chown -R root:dsapp "$VENV"
find "$VENV" -type d -exec chmod 0750 {} +
find "$VENV" -type f -exec chmod u=rw,g=r,o= {} +
find "$VENV/bin" -type f -exec chmod 0750 {} +

# Derive and verify the actual Gunicorn bind from the repository unit template.
EXPECTED_BIND='127.0.0.1:8000'
if [[ -f "$UNIT_FILE" ]]; then
  grep -qF "$EXPECTED_BIND" "$UNIT_FILE" || fail 'Existing app service bind differs from repository configuration.'
else
  unit_tmp="$(mktemp /run/dsapp.service.XXXXXX)"
  sed -e "s|/opt/ds-app/source|$APP_ROOT|g" \
      -e "s|/opt/ds-app/.venv|$VENV|g" \
      -e "s|/etc/dsapp/app.env|$ENV_FILE|g" \
      "$REPO/deploy/systemd/dsapp.service" > "$unit_tmp"
  install -o root -g root -m 0644 "$unit_tmp" "$UNIT_FILE"
  rm -f "$unit_tmp"
fi

# Caddy needs directory traversal only to static assets; no business data is
# served from this path. The collected static tree itself is read-only.
STATIC_ROOT="$(runuser -u dsapp -- /bin/bash -c 'set -a; . "$1"; set +a; cd "$2/app"; "$3/bin/python" manage.py shell --verbosity 0 -c "from django.conf import settings; print(settings.STATIC_ROOT)"' _ "$ENV_FILE" "$APP_ROOT" "$VENV")"
[[ "$STATIC_ROOT" == /* ]] || fail 'DJANGO_STATIC_ROOT must be an absolute path.'
install -d -o dsapp -g dsapp -m 0755 "$STATIC_ROOT"
if [[ "$STATIC_ROOT" == /var/lib/dsapp/* ]]; then chmod 0711 /var/lib/dsapp; fi
SITE_ADDRESSES="$LAN_IP"
if [[ -n "$LAN_HOSTNAME" && "$LAN_HOSTNAME" != "$LAN_IP" ]]; then SITE_ADDRESSES+=", $LAN_HOSTNAME"; fi
cat > "$CADDY_FILE.candidate" <<CADDY
# Managed by dsapp deploy_existing.sh
{
    auto_https disable_redirects
}
$SITE_ADDRESSES {
    bind $LAN_IP
    tls internal
    @outside not remote_ip $LAN_CIDR
    route {
        respond @outside "LAN access only" 403
        handle_path /static/* {
            root * $STATIC_ROOT
            file_server
        }
        handle {
            reverse_proxy $EXPECTED_BIND
        }
    }
}
CADDY
chmod 0644 "$CADDY_FILE.candidate"
caddy fmt --overwrite "$CADDY_FILE.candidate"
printf 'Validating staged Caddy configuration...\n'
caddy validate --adapter caddyfile --config "$CADDY_FILE.candidate" || { rm -f "$CADDY_FILE.candidate"; fail "Caddy validation failed; active config remains unchanged. Backup: $SNAP"; }
install -o root -g root -m 0644 "$CADDY_FILE.candidate" "$CADDY_FILE"
rm -f "$CADDY_FILE.candidate"

# Check schema changes and service config before applying anything to DB.
systemd-analyze verify "$UNIT_FILE"
# systemd environment settings are the same file; read secrets in child shell only.
runuser -u dsapp -- /bin/bash -c 'set -a; . "$1"; set +a; cd "$2/app"; "$3/bin/python" manage.py check --deploy; "$3/bin/python" manage.py migrate --plan' _ "$ENV_FILE" "$APP_ROOT" "$VENV"
runuser -u dsapp -- /bin/bash -c 'set -a; . "$1"; set +a; cd "$2/app"; "$3/bin/python" manage.py migrate' _ "$ENV_FILE" "$APP_ROOT" "$VENV"
runuser -u dsapp -- /bin/bash -c 'umask 022; set -a; . "$1"; set +a; cd "$2/app"; "$3/bin/python" manage.py collectstatic --noinput' _ "$ENV_FILE" "$APP_ROOT" "$VENV"
chown -R dsapp:dsapp "$STATIC_ROOT"
find "$STATIC_ROOT" -type d -exec chmod 0755 {} +
find "$STATIC_ROOT" -type f -exec chmod 0644 {} +
runuser -u dsapp -- /bin/bash -c 'set -a; . "$1"; set +a; cd "$2/app"; "$3/bin/python" manage.py test core --settings=config.postgres_test_settings --keepdb' _ "$TEST_ENV" "$APP_ROOT" "$VENV"
systemctl daemon-reload
systemctl enable --now dsapp.service
systemctl restart dsapp.service
caddy validate --config "$CADDY_FILE"
systemctl reload caddy.service
printf 'Deployment configured. Pre-migration backup: %s\n' "$SNAP"
printf 'Automatic backup timer has not been enabled. Application URL: https://%s/\n' "$LAN_IP"
