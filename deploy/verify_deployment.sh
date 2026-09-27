#!/usr/bin/env bash
# Run with sudo after deploy_existing.sh. Read-only except Django test DB writes.
set -Eeuo pipefail
LAN_IP="${DSAPP_LAN_IP:-192.168.0.41}"
APP_ROOT="${DSAPP_APP_ROOT:-/opt/ds-app/source}"
VENV="${DSAPP_VENV:-/opt/ds-app/.venv}"
ENV_FILE="${DSAPP_ENV_FILE:-/etc/dsapp/app.env}"
TEST_ENV="${DSAPP_TEST_ENV:-/etc/dsapp/test.env}"
fail(){ printf 'FAIL: %s\n' "$*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail 'Run with sudo.'
[[ -r "$ENV_FILE" && -r "$TEST_ENV" ]] || fail 'App/test environment is missing; see inspect_server.sh.'
printf '%s\n' '== Enabled state and service health =='
systemctl is-enabled dsapp.service postgresql.service caddy.service
systemctl is-active dsapp.service postgresql.service caddy.service
systemctl --no-pager --full status dsapp.service caddy.service postgresql.service
systemctl show dsapp.service -p User -p Group -p WorkingDirectory -p ExecStart
printf '%s\n' '== Listener check =='
ss -ltnp
ss -ltn | awk -v https_addr="$LAN_IP:443" '$4 == "127.0.0.1:8000" {app=1} $4 == "127.0.0.1:5432" {pg=1} $4 == https_addr {https=1} END {if(!app) exit 1; print "Gunicorn loopback:8000 present"; if(!pg) exit 2; print "PostgreSQL loopback:5432 present"; if(!https) exit 3; print "HTTPS LAN:443 present"}'  || fail 'Expected application/HTTPS listener missing or bound incorrectly.'
printf '%s\n' '== HTTPS login and static assets =='
headers="$(curl --fail --silent --show-error --insecure --dump-header - "https://$LAN_IP/accounts/login/" --output /tmp/dsapp-login.html)" || fail 'HTTPS login request failed.'
printf '%s\n' "$headers" | head -n 1 | grep -Eq '200' || fail 'Login page did not return HTTP 200.'
grep -q 'name="password"' /tmp/dsapp-login.html || fail 'Login form is missing.'
curl --fail --silent --show-error --insecure "https://$LAN_IP/static/core/app.css" --output /dev/null || fail 'CSS is not served.'
rm -f /tmp/dsapp-login.html
printf '%s\n' '== Django production check =='
runuser -u dsapp -- /bin/bash -c 'set -a; . "$1"; set +a; cd "$2/app"; "$3/bin/python" manage.py check --deploy' _ "$ENV_FILE" "$APP_ROOT" "$VENV"
printf '%s\n' '== PostgreSQL application test suite (separate configured test database) =='
runuser -u dsapp -- /bin/bash -c 'set -a; . "$1"; set +a; cd "$2/app"; "$3/bin/python" manage.py test core --settings=config.postgres_test_settings --keepdb' _ "$TEST_ENV" "$APP_ROOT" "$VENV"
printf '%s\n' 'Verification passed. A real reboot has not been performed.'
