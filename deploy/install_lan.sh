#!/usr/bin/env bash
# Legacy entrypoint; safe resume only. Does not provision live DBs/accounts.
set -Eeuo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/deploy_existing.sh" "$@"
