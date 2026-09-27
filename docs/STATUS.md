# Implementation assessment

No AGENTS.md was present in the repository or parent workspace search. README and existing source were the available project documentation. The initial working tree was clean.

## Implemented and exercised

Django authentication; Employee/Manager/Owner group checks; employee self-service pay/tips; manager corrections; daily and historical business reports; employee date-range reports; employee creation/edit/deactivation; activity logs. Amounts are aggregates; there is no payment-card detail storage.

This iteration adds native Ubuntu/systemd configuration, configurable mounted USB/NAS backup support, recovery instructions, historical manager sales entry, password validation on employee creation, employee sales access restrictions, and correction audit snapshots taken before ModelForm validation mutates instances. Docker deployment files are preserved for legacy installations.

Verification: 15 Django tests on isolated SQLite and 4 backup unit tests with mocked PostgreSQL commands. These verify existing Decimal calculations/report agreement, negative deposits, permission boundaries, self-report isolation, historical sales corrections, prior audit values, invalid financial input, password validation, deactivation, missing mounts, failed backups and retention. No existing database was accessed or migrated. Native services, PostgreSQL concurrency and a real restore drill have not been exercised here.

## Confirmed financial rules

New dates use explicit daily starting cash, ending cash counted **after** employee cash pay and card-tip payouts, and a card batch total **including** tips. Starting cash remains in the drawer. Managers finalize and explicitly reopen closeouts; both actions are audited. Finalized dates reject sales and earnings writes. Financial Django admin screens are read-only to keep changes in the application workflow.

- cash deposit = ending cash − starting cash
- reconstructed cash sales = deposit + cash pay + card tips
- card sales = entered card batch − card tips
- total sales = reconstructed cash sales + card sales
- net daily proceeds = total sales − cash pay = deposit + card batch
- employee earnings = cash pay + card tips + cash tips

Cash tips are tracked as employee earnings, separately from sales and deposits, as in the existing implementation. There is no support for other drawer movements (refunds, expenses, owner withdrawals) or payroll/tax calculations. Negative deposits remain visible; finalization rejects card tips exceeding the batch. Managers must confirm all earnings are recorded before finalization; there is no roster indicating who worked that day.

Migrations 0003 and 0004 add nullable starting cash, ending cash, card batch, and finalization timestamp fields. Existing rows keep nulls and retain the legacy formulas (sales exclude tips and starting float). Existing rows start open; no historical values are rewritten. New forms require all three closeout amounts, and corrections preserve each record's interpretation. These migrations have only been applied to disposable test databases, not an existing deployment.

## Remaining production work

- Test simultaneous submissions and correction conflicts on PostgreSQL.
- Review the legacy CSV importer before using it for real data: it can overwrite earnings without an activity log and does not validate all amounts.
- Validate native service/proxy configuration on the target Ubuntu host, perform actual backup/restore and NAS failure drills, and arrange backup failure monitoring.
- Review the exact LAN/management network and existing rules before any host firewall or SSH changes.
