# Daily Data by shift

Implemented October 11, 2026. This supersedes the consolidated financial-entry
formulas and manual employee-total behavior in DAILY_FINANCIAL_ENTRY.md.

Each date accepts one Day Shift and one Night Shift entry. Save the first shift,
then select the other shift to enter its cash data and employee. Empty shifts are
not automatically created. Each shift has one active employee; both shifts may
use the same employee or different employees. The register keeps a permanent
$205.00 cash reserve, which is never deposited. Removing a positive shift cash
deposit leaves this reserve for the next shift. Negative deposits remain valid
and identify a shortage rather than cash to remove. Monetary inputs default to
$0.00 for new entries only. There is no editable Starting Cash input.
Date and shift cannot be changed while editing a saved entry.

Calculations use Decimal on the server and integer cents in the live preview:

- Gross Total = Total Cash + Total Charges Without Fee.
- Cash Deposit = Total Cash - Employee Pay - STARTING_CASH.

`core/constants.py` defines `STARTING_CASH = Decimal("205.00")`. Each new Day
Shift and Night Shift independently subtracts that same fixed reserve. Neither
employees nor managers can change it through submitted form fields. The preview
receives its reserve from the server; no financial calculation uses floats.
- Credit Card Deposit = Total Charges Without Fee.

Credit card tips, cash tips, and extras are independent amounts. None affect these
three calculations. Negative cash deposits are valid and can be finalized;
monetary displays use -$55.00 formatting. Finalization and reopening apply to the
selected shift, and preserve the existing manager permissions and audit log.

Saving a shift also creates or updates its EmployeeEarning row in the same
transaction. Reassigning an employee updates the same earning row. The existing
uniqueness rule now applies per shift because earnings reference DailySales.
Older independent earnings forms reject writes to consolidated Day Shift entries;
shift pay and tips must be corrected through Daily Data, keeping financial and
employee totals aligned. Self-service reports include both shifts, display the
shift, and count distinct dates. No employee or authentication data is deleted.

Business reports combine both shifts into one row per date and sum those rows
for daily, weekly, monthly, and YTD reports. The daily cash deposit is the sum
of the two shift cash deposits, and the daily credit card deposit is the sum of
the two shift card deposits. Starting Cash is not displayed as an input or
summary value and is never aggregated in reports. A missing shift contributes nothing.
Existing print reports include negative amounts. There is no financial CSV
export endpoint in the current application.

Migration 0007 adds shift, shift_employee, daily_cash_tips, and extras; replaces
unique business_date with unique (business_date, shift); and validates shift
choices and nonnegative tips/extras in the database. It drops no tables and
deletes no rows. Existing rows are assigned Day Shift without guessing an
employee. Existing Starting Cash values are preserved. Pre-consolidation legacy
and drawer records retain their original calculations. Existing consolidated
test records now use the requested formulas, including finalized records; this
was authorized because the stored data is disposable test data. Existing
unattributed manual pay is not automatically allocated. Select the correct
employee when editing such a record. Employee/pay reconciliation conflicts
produce a form error and roll back the save.

Migration 0008 adds `uses_fixed_cash_reserve`. All existing rows receive False,
keeping their original saved reserve and cash-deposit calculations, including
finalized rows. Future rows default to True and use the centralized constant.
The existing starting_cash column stays in place for historical calculations;
new form entries save $205.00 internally for compatibility with the existing
complete-input constraint. Posted reserve values and calculation flags are
ignored. Editing a historical entry preserves its saved reserve and flag. The
live preview uses that saved reserve for those historical entries, matching the
server. No historical input amounts or employee earnings are rewritten.

Verification uses config.test_settings, an isolated in-memory database, and the
forward-migration script. The configured running application database has not
been accessed. Applying to the running development app requires its explicit
environment/settings path. Do not load production credentials or run a reset.

Before any later production release, review the treatment of preexisting
consolidated financial records: these formulas change their displayed totals.
Resolve that accounting policy before applying this development change to a
production database. Apply reviewed migrations, collect static assets, and
restart the intended application only under separate deployment authorization.
