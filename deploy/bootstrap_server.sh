#!/usr/bin/env bash
#
# Bootstrap a CLEAN Ubuntu server for Daiquiri Station.
#
# This script performs one-time host provisioning only.
# It refuses to operate over an existing DS-app installation.
#
# After bootstrap completes, deploy_existing.sh becomes the normal
# deployment/update path.
#
# Run from repository:
#   sudo bash deploy/bootstrap_server.sh
#
set -Eeuo pipefail
umask 077

REPO="${DSAPP_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
APP_ROOT="/opt/ds-app/source"
VENV="/opt/ds-app/.venv"
ENV_DIR="/etc/dsapp"
ENV_FILE="$ENV_DIR/app.env"

fail() {
    printf 'STOP: %s\n' "$*" >&2
    exit 1
}

[[ $EUID -eq 0 ]] || fail "Run with sudo."

[[ -f "$REPO/app/manage.py" ]] ||
    fail "Repository application not found."

[[ -f "$REPO/app/requirements.txt" ]] ||
    fail "requirements.txt not found."

[[ -f "$REPO/deploy/systemd/dsapp.service" ]] ||
    fail "dsapp.service template not found."

# ---------------------------------------------------------
# Refuse to overwrite an existing installation
# ---------------------------------------------------------

[[ ! -e "$ENV_FILE" ]] ||
    fail "$ENV_FILE already exists. Use deploy_existing.sh."

[[ ! -e "$APP_ROOT" ]] ||
    fail "$APP_ROOT already exists. Inspect server before continuing."

if getent passwd dsapp >/dev/null; then
    fail "dsapp service account already exists. Inspect server first."
fi

# ---------------------------------------------------------
# Determine LAN address
# ---------------------------------------------------------

LAN_IP="${DSAPP_LAN_IP:-$(ip route get 1.1.1.1 2>/dev/null |
    awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')}"

[[ -n "$LAN_IP" ]] ||
    fail "Could not determine LAN IP."

printf 'Detected LAN address: %s\n' "$LAN_IP"

# ---------------------------------------------------------
# Install host packages
# ---------------------------------------------------------

printf '%s\n' 'Installing required Ubuntu packages...'

apt-get update

DEBIAN_FRONTEND=noninteractive apt-get install -y \
    postgresql \
    postgresql-client \
    caddy \
    python3 \
    python3-venv \
    python3-dev \
    libpq-dev \
    rsync \
    openssl \
    curl

systemctl enable --now postgresql
systemctl enable --now caddy

# ---------------------------------------------------------
# Create dedicated service account
# ---------------------------------------------------------

printf '%s\n' 'Creating dsapp service account...'

useradd \
    --system \
    --home /nonexistent \
    --shell /usr/sbin/nologin \
    --user-group \
    dsapp

# ---------------------------------------------------------
# Create application directories
# ---------------------------------------------------------

install -d -o root -g dsapp -m 0750 /opt/ds-app
install -d -o root -g dsapp -m 0750 "$APP_ROOT"
install -d -o root -g dsapp -m 0750 "$ENV_DIR"
install -d -o dsapp -g dsapp -m 0711 /var/lib/dsapp

# ---------------------------------------------------------
# Copy repository into production application tree
# ---------------------------------------------------------

printf '%s\n' 'Installing application source...'

rsync -a \
    --exclude='.git/' \
    --exclude='.env' \
    --exclude='.venv/' \
    --exclude='backups/' \
    "$REPO/" "$APP_ROOT/"

chown -R root:dsapp "$APP_ROOT"

find "$APP_ROOT" -type d -exec chmod 0750 {} +
find "$APP_ROOT" -type f -exec chmod 0640 {} +
chmod 0750 "$APP_ROOT/app/manage.py"

# ---------------------------------------------------------
# Create Python virtual environment
# ---------------------------------------------------------

printf '%s\n' 'Creating Python virtual environment...'

python3 -m venv "$VENV"

"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$APP_ROOT/app/requirements.txt"

chown -R root:dsapp "$VENV"

find "$VENV" -type d -exec chmod 0750 {} +
find "$VENV" -type f -exec chmod u=rw,g=r,o= {} +
find "$VENV/bin" -type f -exec chmod 0750 {} +

# ---------------------------------------------------------
# Generate production secrets
# ---------------------------------------------------------

printf '%s\n' 'Generating production credentials...'

DJANGO_SECRET_KEY="$(openssl rand -hex 48)"
POSTGRES_PASSWORD="$(openssl rand -hex 32)"

# ---------------------------------------------------------
# Create PostgreSQL application role and database
# ---------------------------------------------------------

printf '%s\n' 'Creating PostgreSQL application role and database...'

ROLE_EXISTS="$(
    runuser -u postgres -- \
        psql -X -Atqc "SELECT 1 FROM pg_roles WHERE rolname='dsapp'"
)"

[[ -z "$ROLE_EXISTS" ]] ||
    fail "PostgreSQL role dsapp unexpectedly already exists."

DB_EXISTS="$(
    runuser -u postgres -- \
        psql -X -Atqc "SELECT 1 FROM pg_database WHERE datname='dsapp'"
)"

[[ -z "$DB_EXISTS" ]] ||
    fail "PostgreSQL database dsapp unexpectedly already exists."

ROLE_SQL="$(mktemp /run/dsapp-bootstrap-role.XXXXXX)"
chmod postgres:postgres "$ROLE_SQL"
chown 0600 "$ROLE_SQL"

printf "CREATE ROLE dsapp LOGIN PASSWORD '%s' NOSUPERUSER NOCREATEDB NOCREATEROLE;\n" \
    "$POSTGRES_PASSWORD" > "$ROLE_SQL"

runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -f "$ROLE_SQL"

rm -f "$ROLE_SQL"

runuser -u postgres -- createdb \
    --owner=dsapp \
    dsapp

# ---------------------------------------------------------
# Create protected application environment
# ---------------------------------------------------------

printf '%s\n' 'Creating protected application environment...'

cat > "$ENV_FILE" <<EOF
DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=$LAN_IP
DJANGO_CSRF_TRUSTED_ORIGINS=https://$LAN_IP
DJANGO_TIME_ZONE=America/Chicago
DJANGO_STATIC_ROOT=/var/lib/dsapp/static
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=dsapp
POSTGRES_USER=dsapp
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
EOF

chown root:dsapp "$ENV_FILE"
chmod 0640 "$ENV_FILE"

unset DJANGO_SECRET_KEY
unset POSTGRES_PASSWORD

# ---------------------------------------------------------
# Install initial Caddy configuration
# ---------------------------------------------------------

printf '%s\n' 'Preparing Caddy configuration...'

if [[ -f "$REPO/deploy/Caddyfile" ]]; then
    cp "$REPO/deploy/Caddyfile" /etc/caddy/Caddyfile
fi

# ---------------------------------------------------------
# Install systemd application unit
# ---------------------------------------------------------

install \
    -o root \
    -g root \
    -m 0644 \
    "$REPO/deploy/systemd/dsapp.service" \
    /etc/systemd/system/dsapp.service

systemctl daemon-reload

# ---------------------------------------------------------
# Validate bootstrap
# ---------------------------------------------------------

printf '%s\n' 'Testing PostgreSQL application login...'

set +x
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

export PGPASSWORD="$POSTGRES_PASSWORD"

psql \
    -h "$POSTGRES_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    -X \
    -v ON_ERROR_STOP=1 \
    -Atqc 'SELECT 1' >/dev/null

unset PGPASSWORD

printf '\n'
printf '%s\n' 'Bootstrap completed successfully.'
printf 'Application IP: %s\n' "$LAN_IP"
printf '%s\n' 'No Django migrations have been run.'
printf '%s\n' 'No backup timer has been enabled.'
printf '\n'
printf '%s\n' 'Next command:'
printf '%s\n' 'sudo bash deploy/deploy_existing.sh'
