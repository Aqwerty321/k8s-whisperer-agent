#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8010}"
INCIDENT_LIMIT="${INCIDENT_LIMIT:-5}"
AUDIT_LIMIT="${AUDIT_LIMIT:-5}"

printf '== Health ==\n'
curl -fsS "${BASE_URL}/health" | jq

printf '\n== Recent Incidents ==\n'
curl -fsS "${BASE_URL}/api/incidents?limit=${INCIDENT_LIMIT}" | jq '{count, incidents: [.incidents[] | {incident_id, status, anomaly_type, resource_name, plan_action, approved, result}]}'

printf '\n== Recent Audit ==\n'
curl -fsS "${BASE_URL}/api/audit?limit=${AUDIT_LIMIT}" | jq '{count, summaries}'

printf '\n== Tracker State ==\n'
curl -fsS "${BASE_URL}/api/incidents?limit=${INCIDENT_LIMIT}" | jq '{tracked_incidents}'
