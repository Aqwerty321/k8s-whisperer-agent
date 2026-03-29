#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8010}"
INCIDENT_ID="${1:-}"

if [[ -z "${INCIDENT_ID}" ]]; then
  INCIDENT_ID="$(curl -fsS "${BASE_URL}/api/incidents?limit=1" | jq -r '.incidents[-1].incident_id // empty')"
  if [[ -z "${INCIDENT_ID}" ]]; then
    printf 'No incident found to export.\n'
    exit 1
  fi
fi

curl -fsS "${BASE_URL}/api/incidents/${INCIDENT_ID}/report"
