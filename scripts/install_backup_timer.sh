#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(whoami)"

echo "Installing DS App backup service"
echo "User: $APP_USER"
echo "Project: $PROJECT_DIR"

sudo tee /etc/systemd/system/dsapp-backup.service > /dev/null <<SERVICE
[Unit]
Description=DS App PostgreSQL Backup
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
User=$APP_USER
Group=$APP_USER
SupplementaryGroups=docker
WorkingDirectory=$PROJECT_DIR
Environment=DSAPP_PROJECT_DIR=$PROJECT_DIR
ExecStart=$PROJECT_DIR/scripts/backup_db.sh
UMask=0077
SERVICE


sudo tee /etc/systemd/system/dsapp-backup.timer > /dev/null <<'TIMER'
[Unit]
Description=Run DS App PostgreSQL Backup Daily

[Timer]
OnCalendar=*-*-* 02:00:00 America/Chicago
Persistent=true
RandomizedDelaySec=5m

[Install]
WantedBy=timers.target
TIMER


sudo systemctl daemon-reload

sudo systemctl enable --now dsapp-backup.timer

echo
echo "Backup timer installed."
echo

systemctl list-timers dsapp-backup.timer
