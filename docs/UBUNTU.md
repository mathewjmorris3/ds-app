# Permanent Ubuntu deployment (no Docker)

Use a supported Ubuntu Server release with Python 3.10+ and PostgreSQL. The application remains Django/Gunicorn/PostgreSQL/Caddy. Compose files and the old Docker backup scripts are retained for existing installations; do not use those scripts for this native deployment.

These are operator instructions, not an automatic installer. The current `ds-app-01` deployment, application verification, and local restore drill have completed (see [DEPLOYMENT-STATUS.md](DEPLOYMENT-STATUS.md)). No firewall, SSH, router, disk-formatting, or mount configuration has been changed. For a different existing server, inventory services, database versions, ports, backup destinations and Caddy sites first. Review the exact migration plan and verify a backup before changing its database. Do not run the fresh-database steps against an existing database.

## Fresh installation

Install packages and create an unprivileged service account:

```sh
sudo apt update
sudo apt install python3-venv postgresql postgresql-client caddy git
sudo useradd --system --home /var/lib/dsapp --create-home --shell /usr/sbin/nologin dsapp
sudo git clone https://github.com/mathewjmorris3/ds-app.git /opt/ds-app
sudo python3 -m venv /opt/ds-app/.venv
sudo /opt/ds-app/.venv/bin/pip install -r /opt/ds-app/source/app/requirements.txt
sudo install -d -o root -g dsapp -m 0750 /etc/dsapp
sudo install -o root -g dsapp -m 0640 /opt/ds-app/deploy/app.env.example /etc/dsapp/app.env
sudoedit /etc/dsapp/app.env
```

Generate separate secrets with `openssl rand -hex 32` and `openssl rand -hex 64`. Use the first for the database password and the second for Django. Environment files contain plain `KEY=value` assignments, without `export`. Do not commit them. Restrict hostname/origin settings to the actual internal hostname. The default business timezone is America/Chicago; confirm this before entering business data.

The next commands create a **new** database role and database. They do not replace an existing database. If either name exists, stop and inspect it. Assign the role password interactively (use the same value in app.env):

```sh
sudo -u postgres createuser --pwprompt dsapp
sudo -u postgres createdb --owner=dsapp dsapp
```

Keep PostgreSQL listening only on loopback and local sockets; verify with `sudo ss -ltnp`. Verify TCP password authentication works for this role. Any needed change to existing PostgreSQL configuration requires a separate reviewed plan.

Create the static directory and initialize only this new database:

```sh
sudo install -d -o dsapp -g dsapp -m 0755 /var/lib/dsapp/static
sudo -u dsapp bash
set -a
. /etc/dsapp/app.env
set +a
cd /opt/ds-app/source/app
/opt/ds-app/.venv/bin/python manage.py migrate
/opt/ds-app/.venv/bin/python manage.py createsuperuser
/opt/ds-app/.venv/bin/python manage.py collectstatic --noinput
/opt/ds-app/.venv/bin/python manage.py check --deploy
exit
```

Use Django admin to create exact groups `Employee`, `Manager`, `Owner`. Create a normal manager user, assign the Manager group, and associate an active Employee profile with a unique employee number. Managers can then add employees through the application. Owner users get the Owner group and do not need an employee profile for reporting. Do not grant staff/superuser status to ordinary business accounts. Accounts with multiple groups use Owner, then Manager, then Employee precedence.

Install the service:

```sh
sudo install -m 0644 /opt/ds-app/deploy/systemd/dsapp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dsapp
```

Edit a copy of `deploy/Caddyfile`: set the hostname, the server's fixed LAN address and the **actual permitted LAN subnet**. It binds only that address and rejects source addresses outside that subnet. The supplied IPs are examples. Merge the site into existing Caddy configuration if other sites exist; never blindly overwrite it. Validate with `sudo caddy validate --config /etc/caddy/Caddyfile`, then reload Caddy. Create an internal DNS record for the hostname. Distribute Caddy's root certificate to trusted client devices (normally `/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt`); never distribute its private key. Visit the explicit HTTPS URL; HTTP redirect service is disabled.

Verify `8000` and `5432` listen only on loopback, HTTPS works from the intended LAN, outside-subnet requests are rejected, and static CSS loads. Do not forward router ports. No SSH or firewall commands are included: agree on the exact management source subnet and existing rules before changing either. Caddy source filtering is application ingress protection, not a host firewall policy. See [Caddy request matchers](https://caddyserver.com/docs/caddyfile/matchers).

## Automatic USB backups

Use an already prepared Linux filesystem on the USB drive. Identify it with `lsblk -f`; **do not format a drive containing data**. Mount it persistently by filesystem UUID at `/mnt/dsapp-backup` using a reviewed `/etc/fstab` entry (for example ext4 with `defaults,nofail`). Verify with `findmnt /mnt/dsapp-backup`. Only after the mount is present:

```sh
sudo install -d -o dsapp -g dsapp -m 0700 /mnt/dsapp-backup/dsapp
sudo install -o root -g dsapp -m 0640 /opt/ds-app/deploy/backup.env.example /etc/dsapp/backup.env
sudo install -m 0644 /opt/ds-app/deploy/systemd/dsapp-backup.service /etc/systemd/system/
sudo install -m 0644 /opt/ds-app/deploy/systemd/dsapp-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start dsapp-backup.service
sudo journalctl -u dsapp-backup.service -n 50
sudo systemctl enable --now dsapp-backup.timer
```

The destination is configured in backup.env. Missing mounts fail the job, rather than filling the root disk. Dumps use PostgreSQL custom format, archive-list validation, atomic publication, restrictive permissions and a lock preventing overlapping jobs. A failed dump does not prune existing archives. Retention is 7 daily, 4 Sunday, and 12 first-of-month successful archives. Multiple manual runs count toward retention. A missed Sunday/month boundary does not create that tier's archive retrospectively. The timer catches up one missed run after downtime. Review failure logs and `systemctl list-timers dsapp-backup.timer` regularly; external failure notifications are not configured.

Archive-list validation is not a restore test. Complete the restoration drill below before production and periodically thereafter. Securely keep a separate copy of app.env, the deployed Git revision, configuration, and the Caddy CA if retaining client trust is important. Database dumps contain employee/financial information: restrict physical access and use encrypted removable storage where appropriate. Maintain another offline copy; a single attached USB is not disaster protection.

To switch to a NAS, mount its share persistently (NFS or SMB) and provision a directory writable only by the backup service identity. Update BACKUP_MOUNT and BACKUP_ROOT, then run the service manually and perform a restore drill. Ensure the filesystem supports locking and atomic rename, and test unavailable-share behavior. Keep mount credentials in a root-only file outside Git. No application/database changes are needed. A hung NAS job times out after two hours and is reported failed.

## Restoration drill and recovery

Restore into a **new empty database**, never directly over the live database. Use a PostgreSQL client compatible with the source server; record source version and deployed code revision with operational records. Example database name below must be unused:

```sh
sudo -u postgres createdb --owner=dsapp dsapp_restore_check
sudo -u dsapp bash
set -a
. /etc/dsapp/app.env
set +a
export PGPASSWORD="$POSTGRES_PASSWORD"
pg_restore --host=127.0.0.1 --username=dsapp --dbname=dsapp_restore_check --no-owner --no-privileges --single-transaction --exit-on-error /mnt/dsapp-backup/dsapp/daily/SELECTED.dump
export POSTGRES_DB=dsapp_restore_check
cd /opt/ds-app/source/app
/opt/ds-app/.venv/bin/python manage.py check
/opt/ds-app/.venv/bin/python manage.py showmigrations
exit
```

Replace SELECTED.dump with a completed archive. Confirm table counts, sample dates, earnings, deposit totals and activity logs against known records. For UI verification, run a separately configured service against the restored database on a different loopback port and a restricted test hostname; do not repoint production merely to test. See [PostgreSQL pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).

For actual recovery, explain the exact proposed switch first: stop application writes, take a final backup if possible, restore a chosen archive into a new database, verify it with matching code, then change POSTGRES_DB in app.env and restart dsapp. This also directs future backups to the recovered database. Preserve the original database for rollback. Do not apply migrations to a restored database until their effects have been reviewed. Never restore an untrusted archive.

## Updates and checks

Review code and pending migrations, back up and test recovery, stop application writes during schema updates, install dependencies, apply reviewed migrations, collect static files and restart dsapp. Do not automatically migrate on service startup. Keep a rollback plan matching both code and database schema.

Development regression tests (no application database connection):

```sh
cd /opt/ds-app/source/app
../.venv/bin/python manage.py test core --settings=config.test_settings
```

Before deploying to another production host, run the suite with PostgreSQL against a disposable test database, validate Caddy and systemd files on the target, complete a backup/restore drill using that host's intended backup storage, and verify LAN access. The current Ubuntu target's results are recorded in DEPLOYMENT-STATUS.md; the separate local development environment did not have PostgreSQL or Caddy available.

## Migration plan for an existing application database

Migrations 0003 and 0004 add four nullable columns to `core_dailysales`: `starting_cash`, `ending_cash`, `card_batch_total` (decimal amounts), and `finalized_at` (timestamp). Existing records remain legacy sales entries with null new fields; no financial values are recalculated or rewritten. They remain open until a manager finalizes them. These migrations have been applied on `ds-app-01` after a verified pre-migration dump; review their SQL (`manage.py sqlmigrate core 0003` and `0004`) and take a verified backup before applying them to another existing installation. New closeouts use the confirmed drawer rules described in STATUS.md.

For PostgreSQL verification, use `config.postgres_test_settings` with a separately
provisioned `dsapp_test_` database and role. Supply `DSAPP_TEST_DB`,
`DSAPP_TEST_USER`, `DSAPP_TEST_PASSWORD`, and optional `DSAPP_TEST_HOST` and
`DSAPP_TEST_PORT`, then run:

```sh
python manage.py test core --settings=config.postgres_test_settings --keepdb
```

This runs migrations and tests only in that explicitly selected disposable
database. Its role must not own or have access to live business databases. Keep
it without superuser/CREATEDB privileges. The test database remains afterwards;
review its deletion separately. See DEPLOYMENT-STATUS.md for actual host checks.


## Safe administrator scripts for the partially provisioned VM

The current host inventory established that PostgreSQL and Caddy packages are installed, PostgreSQL has an online localhost cluster, `dsapp` exists, `/opt/ds-app/source` and `/opt/ds-app/.venv` exist, the virtualenv was root-only, there is no `dsapp.service`, and Caddy still serves its package default on `:80`. `/etc/dsapp/app.env` and PostgreSQL roles/databases require root inspection. Do not run the old fresh-install provisioning against this host.

Run the following scripts from this checkout in order. Each administrator script should be reviewed before running:

```sh
sudo bash deploy/inspect_server.sh
sudo bash deploy/deploy_existing.sh
sudo bash deploy/verify_deployment.sh
sudo bash deploy/restore_drill.sh
```

`inspect_server.sh` is read-only and hides app and test environment values. `deploy_existing.sh` requires the existing app environment, dsapp user, source tree, and virtualenv; checks free space, app database connectivity, local database host, bind address, and conflicting config; backs up the app environment, any existing test environment, Caddyfile, unit and source tree plus a custom-format database dump to a root-only timestamped directory under `/var/backups/dsapp/predeploy`; then installs repository dependencies/source, validates the staged Caddyfile before replacing/reloading it, creates a fresh uniquely named restricted test role and database as the local PostgreSQL administrator, writes `/etc/dsapp/test.env` with mode 0640 and `root:dsapp` ownership, applies migrations, collects static files, and runs the PostgreSQL suite against that new database. Existing test roles and databases (including `dsapp_test_run`) are left untouched and are never reused because their full grants and purpose cannot be established safely from their names alone. Repeated deployments create new uniquely named test resources; old test resources are retained for manual review/cleanup. PostgreSQL errors are shown with generated credentials redacted. It never creates, drops, or changes the password for the application role/database. If Caddy or systemd differs from the known default/expected deployment, it stops for review. The app uses the repository service's `127.0.0.1:8000` upstream.

The generated test role has no superuser, CREATEDB, or CREATEROLE privileges and owns only its newly created test database. It has no grants on business tables; PostgreSQL's default database CONNECT privilege may still allow a connection, but it does not grant table access. The database is retained after tests and is explicitly disposable. `/etc/dsapp/test.env` is root-owned and readable by the service group; it contains a unique generated password. The scripts do not print password values.

`verify_deployment.sh` checks enabled/active services and listeners, HTTPS login HTML, static CSS, Django deployment checks, and PostgreSQL tests against the dedicated test database. It uses `curl --insecure` because clients must trust Caddy's internal CA; this skips certificate validation only for the check. No firewall rule is changed.

`restore_drill.sh` checks root filesystem free space against the live DB size, makes a mode-0600 custom dump under `/var/backups/dsapp/restore-drills`, asks the local PostgreSQL administrator to create a new timestamp-named database owned by the unprivileged app role, restores under that role's database ownership, compares row counts for sales, earnings, and activity tables, and drops only the temporary database it created. It retains the local dump. This tests archive/restore correctness but cannot protect against loss of the VM or its disk. Automatic backup timers are neither installed nor enabled.

If deployment stops, read its `STOP:` message and do not rerun blindly. Successful migration backup/config snapshots are at `/var/backups/dsapp/predeploy/<UTC timestamp>`; the install script does not overwrite old snapshots. For rollback, use the exact snapshot path printed by the script. Stop dsapp; extract `application-source.tar.gz` to a staging path and verify ownership; copy `app.env`, `Caddyfile`, and the unit file back from that snapshot; then run `systemctl daemon-reload` and validate Caddy. Restore `database-before-migration.dump` into a **new empty database** owned by the configured application role, compare it first, and only then edit `POSTGRES_DB` in `app.env` to the rollback DB. Preserve the current database. Start dsapp and reload Caddy only after checks. Database rollback is not a schema downgrade; the old code must match the restored schema. Do not restore directly over either database. The scripts do not reboot the host or change SSH, firewall, DHCP, DNS, disk formatting, or mount configuration.

The server address currently comes from DHCP as `192.168.0.41`; router reservation is unconfirmed. LAN address/CIDR, optional DNS hostname, application paths, test-environment path, and backup destinations can be overridden through `DSAPP_LAN_IP`, `DSAPP_LAN_CIDR`, `DSAPP_HOSTNAME`, `DSAPP_APP_ROOT`, `DSAPP_VENV`, `DSAPP_ENV_FILE`, `DSAPP_TEST_ENV`, `DSAPP_UNIT_FILE`, `DSAPP_CADDY_FILE`, `DSAPP_CONFIG_BACKUPS`, and `DSAPP_DRILL_ROOT`. When setting a hostname, also add it to `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` in the reviewed app environment before deployment and configure local DNS separately. Local DNS and DHCP reservation remain pending. At present the temporary URL is `https://192.168.0.41/` only after successful deployment and client trust of the internal Caddy CA.

Create the initial administrator interactively (the password is prompted, not embedded):

```sh
sudo runuser -u dsapp -- /bin/bash -c 'set -a; . /etc/dsapp/app.env; set +a; cd /opt/ds-app/source/app; /opt/ds-app/.venv/bin/python manage.py createsuperuser'
```

Use Django admin to create the exact `Manager` group and a normal user. App manager permissions require group membership named `Manager`; staff/superuser is not required for normal application use. To enter the manager's own daily earnings, associate an active `Employee` profile with that user's account. The employee-management screen automatically assigns newly created employee users to the `Employee` group and creates their profile. A Django superuser resolves to Owner in application role checks; it is for initial administration, not ordinary manager work.
