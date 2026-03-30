#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:18010}"
SCENARIO="${1:-crashloop}"

case "${SCENARIO}" in
  crashloop)
    RESOURCE_NAME="$(kubectl get pods -n default -l app=demo-crashloop -o jsonpath='{.items[0].metadata.name}')"
    if [[ -z "${RESOURCE_NAME}" ]]; then
      printf 'No demo-crashloop pod found. Run bash scripts/deploy_demo.sh first.\n'
      exit 1
    fi
    PAYLOAD="$(jq -n --arg resource_name "${RESOURCE_NAME}" '{namespace: "default", seed_events: [{type: "Warning", reason: "BackOff", message: ("Back-off restarting failed container in pod " + $resource_name), namespace: "default", resource_name: $resource_name, resource_kind: "Pod"}]}')"
    ;;
  oomkill)
    RESOURCE_NAME="$(kubectl get pods -n default -l app=demo-oomkill -o json | jq -r '.items | map(select((.metadata.ownerReferences // []) | any(.kind == "ReplicaSet"))) | sort_by(.metadata.creationTimestamp) | last | .metadata.name // empty')"
    if [[ -z "${RESOURCE_NAME}" ]]; then
      printf 'No demo-oomkill pod found. Run bash scripts/deploy_demo.sh first.\n'
      exit 1
    fi
    PAYLOAD="$(jq -n --arg resource_name "${RESOURCE_NAME}" '{namespace: "default", seed_events: [{type: "Warning", reason: "OOMKilled", message: "Container was OOMKilled after hitting memory limit", namespace: "default", resource_name: $resource_name, resource_kind: "Pod"}]}')"
    ;;
  pending)
    PAYLOAD="$(jq -n '{namespace: "default", seed_events: [{type: "Warning", reason: "FailedScheduling", message: "0/1 nodes are available: 1 Insufficient memory.", namespace: "default", resource_name: "demo-pending", resource_kind: "Pod"}]}')"
    ;;
  summary)
    curl -sS "${BASE_URL}/api/incidents" | jq
    exit 0
    ;;
  *)
    printf 'Unknown scenario: %s\n' "${SCENARIO}"
    printf 'Valid scenarios: crashloop, oomkill, pending, summary\n'
    exit 1
    ;;
esac

curl -fsS \
  -X POST "${BASE_URL}/api/incidents/run-once" \
  -H 'Content-Type: application/json' \
  -d "${PAYLOAD}"
