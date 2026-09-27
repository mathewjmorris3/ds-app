# Repository safety

Keep production credentials in `/etc/dsapp/app.env` and dedicated test
credentials in `/etc/dsapp/test.env`, outside this checkout. Never copy their
contents into documentation, issues, or commits. Example environment files use
credential placeholders and safe configuration defaults; replace placeholders
only in the external deployment configuration.

The ignore rules exclude local environment files, private keys, databases,
database dumps, backup archives, logs, imported CSV data, and private uploads.
Source code, migrations, deployment scripts, and the reviewed `.env.example`
files remain versioned. Ignore rules do not protect files already tracked or
remove earlier committed versions. Review the staged diff before each push.

## Review on 2026-09-27

- No AGENTS.md was found in the checkout or its parent directories.
- The configured remote and GitHub main branch were checked against
  `https://github.com/mathewjmorris3/ds-app`.
- All six available commits, all 43 unique historical blobs, tracked paths,
  working files, and pending changes were reviewed for secrets and private data.
- Gitleaks 8.30.1 (release checksum verified) reported no leaks with full
  redaction enabled for history and directory scans. Supplemental checks covered
  credential assignments, environment examples, private keys, tokens, database
  artifacts, archives, logs, and uploads. No sensitive tracked files required
  removal, credential rotation, or history cleanup.
- All 17 Django tests passed with isolated in-memory SQLite settings; all four
  backup unit tests passed. Migration drift, shell syntax, whitespace, and
  representative ignore-rule checks passed.

Scanning is heuristic and cannot prove the absence of secrets or recognize all
business data. This review covers locally available history and files, not
GitHub caches, other clones, unavailable refs, or external deployment storage.
Production credentials were not read or changed. PostgreSQL integration,
deployment, and restore scripts were not executed during this repository audit.

If sensitive material is discovered later, stop pushing, rotate exposed
credentials through the deployment procedure, and coordinate history cleanup
with repository collaborators. Untracking a file alone does not remove history.
