#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8010}"
INCIDENT_ID="${1:-}"
DECISION="${2:-approve}"

if [[ -z "${INCIDENT_ID}" ]]; then
  INCIDENT_ID="$(curl -fsS "${BASE_URL}/api/incidents?status=awaiting_human" | jq -r '.incidents[-1].incident_id // empty')"
  if [[ -z "${INCIDENT_ID}" ]]; then
    printf 'No awaiting_human incident found.\n'
    exit 1
  fi
fi

if [[ "${DECISION}" != "approve" && "${DECISION}" != "reject" ]]; then
  printf 'Decision must be approve or reject.\n'
  exit 1
fi

set -a
. ./.env
set +a

ACTION_ID="approve_incident"
if [[ "${DECISION}" == "reject" ]]; then
  ACTION_ID="reject_incident"
fi

BODY="$(${BASE_URL:+} .venv/bin/python - <<'PY' "${INCIDENT_ID}" "${ACTION_ID}"
import json
import sys
import urllib.parse

incident_id = sys.argv[1]
action_id = sys.argv[2]
payload = {
    "channel": {"id": "C0AP2V8M939"},
    "container": {"message_ts": "fallback-local"},
    "actions": [
        {
            "action_id": action_id,
            "value": json.dumps({"incident_id": incident_id}),
        }
    ],
}
print("payload=" + urllib.parse.quote_plus(json.dumps(payload)))
PY
)"

TIMESTAMP="$(date +%s)"
SIGNATURE="$(BODY="${BODY}" TIMESTAMP="${TIMESTAMP}" SECRET="${SLACK_SIGNING_SECRET:-}" .venv/bin/python - <<'PY'
import hashlib
import hmac
import os

body = os.environ['BODY']
timestamp = os.environ['TIMESTAMP']
secret = os.environ['SECRET']
base_string = f"v0:{timestamp}:{body}".encode('utf-8')
print('v0=' + hmac.new(secret.encode('utf-8'), base_string, hashlib.sha256).hexdigest())
PY
)"

curl -sS \
  -X POST "${BASE_URL}/api/slack/actions" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H "X-Slack-Request-Timestamp: ${TIMESTAMP}" \
  -H "X-Slack-Signature: ${SIGNATURE}" \
  --data "${BODY}" >/dev/null

for _ in {1..20}; do
  STATUS="$(curl -fsS "${BASE_URL}/api/incidents/${INCIDENT_ID}" | jq -r '.status')"
  if [[ "${STATUS}" != "awaiting_human" ]]; then
    break
  fi
  sleep 1
done

curl -fsS "${BASE_URL}/api/incidents/${INCIDENT_ID}" | jq '{incident_id, status, approved, result, slack_message_ts}'
