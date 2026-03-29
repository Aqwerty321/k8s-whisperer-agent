#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8010}"
KEEP_INCIDENTS="${KEEP_INCIDENTS:-5}"
KEEP_AUDIT_ENTRIES="${KEEP_AUDIT_ENTRIES:-5}"

curl -fsS \
  -X POST "${BASE_URL}/api/demo/prune" \
  -H 'Content-Type: application/json' \
  -d "{\"keep_incidents\": ${KEEP_INCIDENTS}, \"keep_audit_entries\": ${KEEP_AUDIT_ENTRIES}}" | jq
