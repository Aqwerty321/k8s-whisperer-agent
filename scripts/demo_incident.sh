#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8010}"
SCENARIO="${1:-crashloop}"

case "${SCENARIO}" in
  crashloop)
    PAYLOAD='{
      "namespace": "default",
      "seed_events": [
        {
          "type": "Warning",
          "reason": "BackOff",
          "message": "Back-off restarting failed container in pod demo-crashloop",
          "namespace": "default",
          "resource_name": "demo-crashloop",
          "resource_kind": "Pod"
        }
      ]
    }'
    ;;
  oomkill)
    PAYLOAD='{
      "namespace": "default",
      "seed_events": [
        {
          "type": "Warning",
          "reason": "OOMKilled",
          "message": "Container was OOMKilled after hitting memory limit",
          "namespace": "default",
          "resource_name": "demo-oomkill",
          "resource_kind": "Pod"
        }
      ]
    }'
    ;;
  pending)
    PAYLOAD='{
      "namespace": "default",
      "seed_events": [
        {
          "type": "Warning",
          "reason": "FailedScheduling",
          "message": "0/1 nodes are available: 1 Insufficient memory.",
          "namespace": "default",
          "resource_name": "demo-pending",
          "resource_kind": "Pod"
        }
      ]
    }'
    ;;
  *)
    printf 'Unknown scenario: %s\n' "${SCENARIO}"
    printf 'Valid scenarios: crashloop, oomkill, pending\n'
    exit 1
    ;;
esac

curl -sS \
  -X POST "${BASE_URL}/api/incidents/run-once" \
  -H 'Content-Type: application/json' \
  -d "${PAYLOAD}"
