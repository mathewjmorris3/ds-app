#!/usr/bin/env bash
# Read-only privileged inventory. Run from any checkout: sudo bash deploy/inspect_server.sh
set -Eeuo pipefail
printf '%s\n' '== Host, disk, and addresses =='
hostnamectl --static
ip -brief -4 address
df -h /
lsblk -f
printf '%s\n' '== Relevant packages =='
dpkg-query -W -f='${binary:Package} ${Version}\n' 'postgresql*' caddy python3-venv python3-dev libpq-dev 2>/dev/null || true
printf '%s\n' '== Service account =='
getent passwd dsapp || true
getent group dsapp || true
printf '%s\n' '== PostgreSQL clusters, roles, and database names (no secrets) =='
if command -v pg_lsclusters >/dev/null; then pg_lsclusters; fi
if id postgres >/dev/null 2>&1; then
  runuser -u postgres -- psql -X -P pager=off -c 'SELECT datname, pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datallowconn ORDER BY datname;' || true
  runuser -u postgres -- psql -X -P pager=off -c "SELECT rolname, rolsuper, rolcreatedb, rolcanlogin FROM pg_roles WHERE rolname NOT LIKE 'pg_%' ORDER BY rolname;" || true
fi
printf '%s\n' '== Application deployment paths =='
for path in /etc/dsapp /etc/systemd/system/dsapp.service /opt/ds-app /var/lib/dsapp; do
  if [[ -e "$path" ]]; then stat -c '%A %U:%G %n' "$path"; else printf 'missing: %s\n' "$path"; fi
done
if [[ -f /etc/dsapp/app.env ]]; then
  printf '%s\n' 'app.env keys present (values hidden):'
  sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1=<hidden>/p' /etc/dsapp/app.env
fi
if [[ -f /etc/dsapp/test.env ]]; then
  printf '%s\n' 'test.env keys present (values hidden):'
  sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1=<hidden>/p' /etc/dsapp/test.env
fi
printf '%s\n' '== Unit state and definitions =='
systemctl --no-pager --full status dsapp caddy postgresql 2>&1 || true
systemctl cat dsapp 2>&1 || true
printf '%s\n' '== Listening TCP sockets =='
ss -ltnp
printf '%s\n' '== Caddy config and validation =='
if [[ -f /etc/caddy/Caddyfile ]]; then sed -n '1,180p' /etc/caddy/Caddyfile; caddy validate --config /etc/caddy/Caddyfile || true; fi
printf '%s\n' '== Backup timers (must remain disabled) =='
systemctl is-enabled dsapp-backup.timer 2>/dev/null || true
systemctl list-timers dsapp-backup.timer --no-pager 2>/dev/null || true
