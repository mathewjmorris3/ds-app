# Daily financial entry redesign

Implemented in the workspace development branch `dev/daily-financial-entry`.
No running service, deployment environment, secret file, or application database
was modified. The source models/views at `/opt/ds-app/source/app` matched the
checkout's original versions. Live records were not queried: this checkout has
no designated development database configuration, and the installed service
must not be assumed to be `ds-app-dev`.

## Existing architecture and affected components

The existing closeout is `core.DailySales`, not `DailyCloseout`.
`EmployeeEarning.daily_sales` links each employee's `cash_pay`, `card_tips`, and
`cash_tips` to a business date, with a per-employee/day unique constraint.
Legacy records store cash/card sales before tips. Drawer closeouts store starting
cash, cash remaining after payouts, and card batch including tips. Those meanings
and correction forms remain available for historical dates.

Financial writes remain restricted to Managers and superusers; ordinary Owners
are read-only. Employees retain their existing own-earnings entry and viewing
permissions. Existing login, CSRF, finalization/reopening, employee management,
and activity access rules remain enforced on the server.

`reports()` handles daily, weekly, monthly, and YTD business reports. Its tabs,
date selector, printing, and individual earnings table remain. New financial
summaries and daily breakdowns include all eight new inputs/results separately
from historical business summaries. Employee tables include individual earnings
from all record types. The dashboard has navigation cards rather than financial
calculations; its Manager Daily Data link now opens consolidated financial entry.
The admin is read-only and displays the new totals. The CSV importer remains
restricted to open legacy records. The old `daily_closeout.html` template has no
URL/view connection and is not the active form.

## Accounting and schema

Migration `0005_dailysales_card_charges_dailysales_daily_card_tips_and_more`
adds nullable Decimal(12,2) columns:

| Column | Meaning |
|---|---|
| register_cash | Total Cash from Register, after credit card tips removed |
| card_charges | Credit Card Charges Without Fee |
| daily_card_tips | Manual daily Credit Card Tips |
| daily_employee_pay | Manual daily Employee Pay |

`starting_cash` is reused. Its **form** default is $205.00 for new records;
historical NULLs are not replaced. All five financial amounts are required in
new entries, nonnegative, and limited to $9,999,999,999.99 per input. Values with
more than two fractional digits are rejected instead of rounded. Whole amounts
and one fractional digit are accepted and persisted at two-place precision.

Migration `0006_dailysales_complete_daily_financial_inputs_and_more` adds checks
requiring either all four new fields to be NULL (historical), or all new fields
and starting cash to be present, nonnegative, with old drawer count/batch fields
NULL (consolidated). Existing unique business dates remain enforced.

No data migration or backfill is included. Existing migrations are untouched.
New totals are unavailable (`None`) for historical records. There are no
assumptions converting historical sales into register cash or inclusive totals.

Server totals use Decimal properties, with formulas preserved exactly:

```text
Subtotal = register_cash + card_charges
Total Deposit = Subtotal + daily_card_tips
Cash Deposit = Total Deposit - daily_employee_pay - starting_cash - card_charges
```

Calculated totals are derived from saved inputs, not stored in extra columns.
ActivityLog captures original/new inputs and derived totals, actor, and timestamp
in the same transaction as financial changes. Client-submitted calculated fields
are ignored. Browser previews use BigInt integer cents to avoid floating-point
rounding, and update on input events. Invalid/missing inputs show an unavailable
preview. Cash Deposit is prominent and negative results show a review warning;
negative results can be saved for review but cannot be finalized until corrected.

Manual daily pay and tips are independent control totals. They are **not** added
to the employee-level totals, and financial entry never creates EmployeeEarning
records. Individual credit card tips and cash tips still appear in employee
reports. Employee edits do not change manual daily inputs; Managers reconcile
those totals manually. Starting cash in period summaries is the sum of each
day's retained float, not an opening balance for the entire period.

Saving a new record against an existing consolidated date requires first loading
that record; a hidden record ID distinguishes explicit edits from duplicate
submissions. The database unique constraint handles concurrent creates, and
existing-date writers use row locking. New financial record dates are immutable
when editing. Finalized records require reopening before any inputs/earnings
can change.

## Validation performed

From `app/`, using the existing Python environment and isolated settings:

```bash
/opt/ds-app/.venv/bin/python manage.py check --settings=config.test_settings
/opt/ds-app/.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.test_settings
/opt/ds-app/.venv/bin/python manage.py test --settings=config.test_settings
```

Results: no system check issues; no ungenerated model changes; 30 tests passed.
Tests cover the $1,470.00/$1,565.00/$560.00 example, exact cents, zero inputs,
default date/float, required/invalid/negative/oversized inputs, duplicate creates
and explicit edits, authentication/roles/CSRF, persistence and database checks,
financial and employee independence, finalization, mixed historical reporting
in every period, activity snapshots, and atomic rollback on audit failure.

From the repository root:

```bash
/opt/ds-app/.venv/bin/python scripts/test_daily_financial_migration.py
```

Passed: a fresh isolated in-memory database was migrated to 0004, populated with
legacy sales/drawer/employee fixtures, then migrated forward. All original values
and records survived, and new inputs remained NULL.

The actual browser JavaScript was executed in a V8 runtime against a mock DOM:
example, cents, zero, negative warning, invalid precision, missing input, maximum,
and input-event recalculation passed. A full browser/layout session and a
PostgreSQL integration run remain development deployment checks; no browser
or dedicated PostgreSQL test credentials were available here.

## Development rollout

1. Identify the actual `ds-app-dev` checkout, virtualenv, systemd unit, static
   directory, and database. Do not use the existing deployment script's defaults
   until verified: they target `/opt/ds-app/source` and `dsapp.service` and do not
   establish a dev/prod distinction.
2. Before migrating, take a normal database backup and record an inventory using
   the development database connection only. These SQL queries are read-only:

   ```sql
   SELECT count(*) AS closeouts,
          count(*) FILTER (WHERE starting_cash IS NULL) AS legacy_sales,
          count(*) FILTER (WHERE starting_cash IS NOT NULL) AS drawer_closeouts
   FROM core_dailysales;
   SELECT count(*) AS employee_earnings FROM core_employeeearning;
   SELECT count(*) AS incomplete_drawer_records FROM core_dailysales
   WHERE starting_cash IS NOT NULL
     AND (ending_cash IS NULL OR card_batch_total IS NULL);
   ```

   Investigate incomplete existing drawers without inventing missing values.
3. Install/review this branch in the development checkout using its existing
   environment configuration. No new Python dependencies are required. Run the
   three verification commands above and the forward migration fixture script.
4. Run the full suite on a separately provisioned disposable PostgreSQL test
   database using the repository's `config.postgres_test_settings` and `--keepdb`
   workflow in `docs/UBUNTU.md`. Never point tests at the development/live DB.
5. With the **development** environment loaded and its connection confirmed, run
   `python manage.py migrate --plan`, then `python manage.py migrate`, followed
   by `python manage.py collectstatic --noinput` using that environment's Python.
   Restart only the confirmed development Gunicorn unit.
6. In a browser, verify the example on desktop/tablet/mobile, save/reload/edit,
   duplicate submissions, employee earnings, negative deposit review,
   finalize/reopen, audit details, and all report periods. Confirm the preexisting
   row counts and historical values are unchanged.

## Production considerations

Production deployment is not performed or authorized by this change. After
successful development verification, schedule a separately approved production
release with backup and schema review. Additive columns and check constraints
can acquire table locks; review table size and PostgreSQL lock duration before
migrating. Avoid writes from older application workers during the rollout and
ensure all workers/static assets run the matching version.

Do not backfill historical financial inputs unless underlying source data is
available and a separate audited conversion is approved. Do not reverse these
migrations after new financial records have been created: dropping their input
columns would lose accounting data. Retain the schema and use a reviewed
forward fix if an issue is discovered.

## Changed files

- `app/core/models.py`, `forms.py`, `views.py`, `admin.py`
- `app/core/templates/core/manage_sales.html`, `reports.html`, `dashboard.html`, `enter_today.html`
- `app/core/static/core/daily_financial.js`
- `app/core/management/commands/import_dummy_csv.py`
- `app/core/tests.py`
- New migrations `0005` and `0006`
- `scripts/test_daily_financial_migration.py`
- This document
