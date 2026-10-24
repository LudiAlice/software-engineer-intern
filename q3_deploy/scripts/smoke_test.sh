#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# The Python driver runs inside api; requests still go through nginx.
docker compose --env-file .env.example exec -T api python q3_deploy/scripts/smoke_test.py --base "${BASE:-http://nginx}"
