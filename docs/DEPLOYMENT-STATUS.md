# Deployment status — 2026-09-26

## Deployment, application verification, and local restore drill complete

- Host: `ds-app-01`, Ubuntu 26.04 VM at `192.168.0.41/24`. DHCP reservation and local DNS remain unconfirmed.
- Native deployment completed from `deploy/deploy_existing.sh`. Django, psycopg, and Gunicorn were already installed in the application virtualenv; Caddy and PostgreSQL were already installed.
- Before migration, the script saved and validated a custom-format dump and configuration snapshot at `/var/backups/dsapp/predeploy/20260926T234132Z`. An earlier attempt's verified snapshot is at `/var/backups/dsapp/predeploy/20260926T233728Z`.
- Migrations `contenttypes`, `auth`, `admin`, `core` 0001–0004, and `sessions` completed. Existing app database role/database were not provisioned or reset. The app role remains without `SUPERUSER` or `CREATEDB`.
- Static collection copied 128 files to `/var/lib/dsapp/static`.
- PostgreSQL test suite passed: 17 tests, 0 failures. The deployment wrote the restricted test environment before verification needs it. Older test resources were not dropped.
- The `dsapp.service` unit was enabled and restarted. Caddy's staged config validated; the deployment script validated and reloaded the active Caddy config. Configured URL: `https://192.168.0.41/`.
- `deploy/verify_deployment.sh` passed: all services enabled/active; Gunicorn on `127.0.0.1:8000`, PostgreSQL on `127.0.0.1:5432`, and Caddy HTTPS on `192.168.0.41:443`; HTTPS login and static CSS requests passed; 17 PostgreSQL tests passed again.
- `deploy/restore_drill.sh` passed using local persistent storage. It retained `/var/backups/dsapp/restore-drills/20260926T235010Z.dump`, restored to a distinct temporary database, matched row counts (`core_dailysales`, `core_employeeearning`, `core_activitylog`: `0:0:0`), and removed only that temporary database. The archive is not off-host protection.
- Caddy obtained its internal CA certificate but its attempt to install the root certificate into the server trust store failed because the service could not execute sudo. Browser trust on each client remains to be configured; the verification requests used `curl --insecure`.
- `manage.py check --deploy` reported the advisory `security.W004` because HSTS is unset. HSTS was not enabled automatically.
- Scheduled backups remain disabled. No USB/NAS destination is mounted or configured. The completed local restore drill does not protect against VM/disk loss.

## Still to verify or configure

- The deployment output and HTTP checks do not verify browser login or LAN client trust of Caddy's internal CA.
- Create the initial Django administrator interactively, then create the exact `Manager` group and manager user in Django admin. App manager access is group-based; a normal manager need not be Django staff/superuser. To record their own earnings, the manager also needs an active `Employee` profile.
- Perform a controlled reboot and rerun service verification to confirm observed post-reboot startup. No reboot has been performed.
- Confirm DHCP reservation and configure internal DNS before treating the IP/hostname as permanent. No firewall, SSH, router, disk formatting, or mount changes were made.

The first restore-drill attempt stopped because the PostgreSQL OS account could not read the root-only partial dump. `restore_drill.sh` now passes the already-open root-owned file descriptor to `pg_restore` on standard input; the successful retry retained the dump at mode 0600. No restore attempt touched the live database.

## Safe administrator sequence

Run these from the repository checkout, reviewing each script before use:

```sh
sudo bash deploy/inspect_server.sh
sudo bash deploy/deploy_existing.sh
sudo bash deploy/verify_deployment.sh
sudo bash deploy/restore_drill.sh
```

`inspect_server.sh` is read-only and hides environment values. `deploy_existing.sh` snapshots configuration and the live database before migrations, uses new uniquely named restricted test resources, creates `/etc/dsapp/test.env` securely, installs the app service, and configures Caddy for internal HTTPS on the LAN address. Existing test roles/databases are preserved. PostgreSQL admin commands use local peer authentication; the `dsapp` role is never granted database-creation or superuser privileges. Review `docs/UBUNTU.md` for restore, rollback, manager setup, and backup destination guidance.

Automatic backup timers remain disabled until prepared USB or NAS storage is mounted and configured. Do not format disks. Local dump archives are stored under restricted `/var/backups/dsapp/restore-drills`; they do not protect against loss of the VM or its disk. No automatic reboot, SSH/firewall change, DHCP reservation, DNS record, or mount configuration has been applied.
