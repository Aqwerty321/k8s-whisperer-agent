#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8010}"
SCENARIO="${1:-crashloop}"

case "${SCENARIO}" in
  crashloop)
    RESOURCE_NAME="$(kubectl get pods -n default -l app=demo-crashloop -o jsonpath='{.items[0].metadata.name}')"
    if [[ -z "${RESOURCE_NAME}" ]]; then
      printf 'No demo-crashloop pod found. Run bash scripts/deploy_demo.sh first.\n'
      exit 1
    fi
    PAYLOAD="$(printf '{\n  \"namespace\": \"default\",\n  \"seed_events\": [\n    {\n      \"type\": \"Warning\",\n      \"reason\": \"BackOff\",\n      \"message\": \"Back-off restarting failed container in pod %s\",\n      \"namespace\": \"default\",\n      \"resource_name\": \"%s\",\n      \"resource_kind\": \"Pod\"\n    }\n  ]\n}' "${RESOURCE_NAME}" "${RESOURCE_NAME}")"
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
