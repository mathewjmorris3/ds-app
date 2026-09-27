# DS Business Management Application

A self-hosted business management application for recording daily sales, employee earnings, tips, employee information, reporting, and activity history.

The target deployment is a permanent Ubuntu server on a private local network, using Django, PostgreSQL, Caddy and systemd without Docker.

Start with [native Ubuntu installation and recovery](docs/UBUNTU.md) and [implementation status and financial rules](docs/STATUS.md). The Docker instructions below are retained as legacy deployment documentation.

## Purpose

The application replaces manual paper-based daily business records with a centralized system for tracking:

- Daily cash sales
- Credit/debit card sales
- Employee cash pay
- Credit card tips
- Cash tips
- Employee earnings
- Daily, weekly, monthly, and year-to-date business reports
- Individual employee earnings reports
- Employee information
- Management activity logs

The application is intended for small-business internal use.

---

## Architecture

```text
Client Browser
      |
      | HTTPS
      v
+------------------+
|      Caddy       |
| Reverse Proxy    |
| TLS Termination  |
+------------------+
      |
      | Docker Network
      v
+------------------+
|    Gunicorn      |
|      Django      |
+------------------+
      |
      v
+------------------+
|   PostgreSQL     |
+------------------+
```

Technitium DNS Server provides local DNS resolution.

Development hostname:

```text
https://dsapp.home.arpa
```

---

## Technology Stack

| Component | Purpose |
|---|---|
| Ubuntu Server | Application host |
| Docker Engine | Container runtime |
| Docker Compose | Application orchestration |
| Django | Web application framework |
| Gunicorn | Production WSGI server |
| PostgreSQL | Application database |
| Caddy | HTTPS reverse proxy and static file server |
| Technitium DNS | Local DNS services |
| Git / GitHub | Source control and deployment |

---

## User Roles

### Employee

Employees can:

- Enter their own daily earnings
- View their own earnings
- View weekly, monthly, yearly, and custom earnings reports

Employees cannot:

- View other employee earnings
- View business-wide financial reports
- Manage employees
- View administrative activity logs

### Manager

Managers can:

- Perform employee functions
- Enter or correct employee earnings
- Enter and modify daily sales data
- View business reports
- Add employees
- Edit employee information
- Deactivate employee accounts
- Review application activity logs

Manager corrections are recorded in the activity log.

### Owner

Owners primarily have reporting and oversight access.

Owners can:

- View business reports
- View employee information
- Review historical business data

The Owner role is intended primarily for business oversight rather than daily data entry.

### Administrator

Django administrator accounts are reserved for application administration and development.

Administrative accounts should not be used for normal business operations.

---

## Financial Data

### Daily Sales

The application tracks:

- Cash sales
- Credit/debit card sales

### Employee Earnings

The application tracks:

- Cash pay
- Credit card tips
- Cash tips

Employee earnings are associated with both an employee and a business date.

> Note: support for subtracting a starting cash drawer amount from the ending cash count is planned and should be validated before production use if the business relies on a fixed drawer float.

---

## Reports

Business reports support:

- Daily
- Weekly
- Monthly
- Year-to-date

Employee earnings reports support:

- Weekly
- Monthly
- Year-to-date
- Yearly
- Custom date ranges

Employee earnings reports are informational and are not intended to serve as:

- W-2 forms
- Pay stubs
- Tax statements
- Official lender income verification

---

## Activity Logging

Important application changes are recorded, including:

- Employee creation
- Employee modification
- Employee deactivation
- Sales changes
- Employee earnings corrections

Activity records may include:

- User performing the action
- Action performed
- Object affected
- Timestamp
- Previous values
- Updated values

---

## Project Structure

```text
ds-app/
├── app/
│   ├── config/
│   ├── core/
│   ├── manage.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── backups/
│   ├── daily/
│   ├── weekly/
│   └── monthly/
│
├── caddy/
│   └── Caddyfile
│
├── scripts/
│   ├── backup_db.sh
│   └── install_backup_timer.sh
│
├── staticfiles/
├── .env
├── .env.example
├── .gitignore
├── compose.yaml
├── LICENSE
└── README.md
```

The following should never be committed to Git:

```text
.env
Database backups
Private certificates
Imported financial CSV files
PostgreSQL database data
```

These items should be excluded through `.gitignore`.

---

## Environment Configuration

Application-specific configuration is stored in:

```text
.env
```

A template should be provided as:

```text
.env.example
```

For a new deployment:

```bash
cp .env.example .env
nano .env
```

Sensitive values such as passwords and Django secret keys must be unique for each deployment.

Generate a PostgreSQL password with:

```bash
openssl rand -hex 32
```

Generate a Django secret value with:

```bash
openssl rand -hex 64
```

Never commit the resulting `.env` file.

---

## Docker Deployment

After Docker Engine and the Docker Compose plugin are installed:

```bash
git clone https://github.com/mathewjmorris3/ds-app.git
cd ds-app
```

Create the environment configuration:

```bash
cp .env.example .env
nano .env
```

Build and start the application:

```bash
docker compose up -d --build
```

Check container status:

```bash
docker compose ps
```

Expected services include:

```text
ds-app-db
ds-app-web
ds-app-caddy
ds-app-dns
```

---

## Django Database Setup

For a new database, apply migrations:

```bash
docker compose exec web python manage.py migrate
```

Create the initial administrative account:

```bash
docker compose exec web python manage.py createsuperuser
```

Collect static files if needed:

```bash
docker compose exec web python manage.py collectstatic --noinput
```

---

## Application Access

The application is intended to be accessed through HTTPS.

Development example:

```text
https://dsapp.home.arpa
```

Direct access to Gunicorn port `8000` should not be exposed to the LAN.

External access should not be enabled through router port forwarding unless a separate secure remote-access design is implemented.

---

## HTTPS

Caddy provides HTTPS for the application.

For LAN-only deployments, Caddy can use its internal certificate authority. Each client device must trust the Caddy root certificate before the browser will show the application as fully trusted.

A future deployment may instead use a registered domain and publicly trusted TLS certificate.

---

## DNS

Technitium DNS Server provides internal DNS resolution.

Example records:

```text
dsapp.home.arpa    -> Application server
dns.home.arpa      -> DNS server
```

Client devices should use the internal DNS server for DNS resolution.

Using a public DNS provider directly as a secondary client DNS server may cause internal hostnames to fail intermittently because the public resolver does not know the private `home.arpa` records.

---

## Database Backups

PostgreSQL backups are generated by:

```text
scripts/backup_db.sh
```

Current retention target:

| Backup Type | Retention |
|---|---:|
| Daily | 7 |
| Weekly | 4 |
| Monthly | 12 |

Run a backup manually:

```bash
./scripts/backup_db.sh
```

Backups are stored under:

```text
backups/
```

The automated backup timer can be installed with:

```bash
./scripts/install_backup_timer.sh
```

Check the timer:

```bash
systemctl list-timers dsapp-backup.timer
```

Check backup logs:

```bash
journalctl -u dsapp-backup.service
```

Database backups are intentionally excluded from Git.

A production deployment should also maintain a backup copy on another physical device or storage system.

---

## Backup and Recovery Model

Git and database backups protect different things.

### Git protects

- Application source code
- Docker configuration
- Deployment scripts
- Django templates
- Configuration templates

### Database backups protect

- Sales history
- Employee earnings
- Employee records
- Activity logs
- Business data

Cloning the Git repository alone does **not** restore existing business data.

A complete recovery may require:

1. The Git repository
2. A valid `.env` configuration
3. A PostgreSQL database backup
4. Required local DNS configuration
5. Required TLS trust configuration

---

## Current Development Environment

The current development environment uses:

```text
Server: ds-app-01
IP:     192.168.0.11
DNS:    dsapp.home.arpa
```

These values are environment-specific and should not be assumed for another deployment.

The production/business deployment may use a different:

- IP address
- Ubuntu hostname
- DNS configuration
- VMware networking configuration

---

## Planned Business Deployment

The intended deployment architecture is:

```text
Business Laptop
      |
      v
VMware
      |
      v
Ubuntu Server VM
      |
      v
Docker Compose
      |
      +-- PostgreSQL
      +-- Django / Gunicorn
      +-- Caddy
      +-- Technitium DNS
```

The long-term goal is for a new system to be deployable primarily through:

```bash
git clone https://github.com/mathewjmorris3/ds-app.git
cd ds-app

cp .env.example .env
nano .env

docker compose up -d --build
```

Additional initialization and recovery steps should be documented as deployment is finalized.

---

## Security

Current security measures include:

- HTTPS application access
- Caddy TLS termination
- Django `DEBUG=False`
- Secure session cookies
- Secure CSRF cookies
- CSRF trusted origins
- Django role-based access control
- Server-side authorization checks
- PostgreSQL isolated through Docker networking
- Gunicorn instead of Django's development server
- Activity logging
- Git secret exclusions
- Automated PostgreSQL backups

Planned additional hardening includes:

- Ubuntu host firewall
- Restricted management ports
- Backup replication
- Restore testing
- Application health monitoring
- Documented recovery procedures

---

## Updating the Application

After changes are committed and pushed:

```bash
cd ~/ds-app
git pull
```

If dependencies, images, or Compose configuration changed:

```bash
docker compose up -d --build
```

Apply migrations when required:

```bash
docker compose exec web python manage.py migrate
```

Collect static files when required:

```bash
docker compose exec web python manage.py collectstatic --noinput
```

Check status:

```bash
docker compose ps
```

---

## Git Workflow

Typical development workflow:

```bash
git status
git add .
git commit -m "Describe the change"
git push
```

Before committing, verify that `.env`, database dumps, certificates, and business data are not staged.

---

## Important Deployment Rule

Never commit secrets or production business data.

Do not add:

```text
.env
Database dumps
Private TLS keys or CA material
Employee financial CSV exports
Production passwords
Django secret keys
```

to the repository.

---

## Status

Current major components:

- [x] Django application
- [x] PostgreSQL database
- [x] Employee authentication
- [x] Role-based permissions
- [x] Daily sales entry
- [x] Employee earnings entry
- [x] Business reporting
- [x] Employee reporting
- [x] Employee management
- [x] Activity logging
- [x] Gunicorn production application server
- [x] Caddy HTTPS reverse proxy
- [x] Local DNS
- [ ] Automatic backups (disabled until USB/NAS destination is configured)
- [ ] Backup restore testing
- [ ] Ubuntu firewall hardening
- [x] Safe resume scripts for inspecting and completing native deployment
- [ ] Business production deployment
- [ ] Production recovery documentation

---

## License

See the `LICENSE` file in this repository for the licensing terms.
