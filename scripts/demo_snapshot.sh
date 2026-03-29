#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8010}"
INCIDENT_LIMIT="${INCIDENT_LIMIT:-5}"
AUDIT_LIMIT="${AUDIT_LIMIT:-5}"

printf '== Health ==\n'
curl -fsS "${BASE_URL}/health" | jq

printf '\n== Scoreboard ==\n'
incidents_json="$(curl -fsS "${BASE_URL}/api/incidents?limit=${INCIDENT_LIMIT}")"
audit_json="$(curl -fsS "${BASE_URL}/api/audit?limit=${AUDIT_LIMIT}")"
printf '%s\n' "${incidents_json}" | jq '{recent_incident_count: .count, by_status: (.incidents | group_by(.status) | map({key: .[0].status, value: length}) | from_entries), awaiting_human: ([.incidents[] | select(.awaiting_human == true)] | length)}'
printf '%s\n' "${audit_json}" | jq '{recent_audit_count: .count, by_decision: (.summaries | group_by(.decision) | map({key: .[0].decision, value: length}) | from_entries)}'

printf '\n== Recent Incidents ==\n'
printf '%s\n' "${incidents_json}" | jq '{count, incidents: [.incidents[] | {incident_id, status, anomaly_type, resource_name, plan_action, approved, result}]}'

printf '\n== Recent Audit ==\n'
printf '%s\n' "${audit_json}" | jq '{count, summaries}'

printf '\n== Tracker State ==\n'
printf '%s\n' "${incidents_json}" | jq '{tracked_incidents}'
