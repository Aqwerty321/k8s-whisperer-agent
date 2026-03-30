#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8010}"
INCIDENT_ID="${1:-}"

if [[ -z "${INCIDENT_ID}" ]]; then
  INCIDENT_ID="$(curl -fsS "${BASE_URL}/api/incidents?limit=1" | jq -r '.incidents[-1].incident_id // empty')"
fi

if [[ -z "${INCIDENT_ID}" ]]; then
  printf 'No incident found for Soroban proof.\n'
  exit 1
fi

printf '== Incident ==\n'
printf 'incident_id=%s\n' "${INCIDENT_ID}"

printf '\n== Backend Proof Payload ==\n'
curl -fsS "${BASE_URL}/api/attest/${INCIDENT_ID}/proof" | jq

printf '\n== Anchor Incident ==\n'
curl -fsS -X POST "${BASE_URL}/api/attest" -H 'Content-Type: application/json' -d "{\"incident_id\":\"${INCIDENT_ID}\"}" | jq

printf '\n== Verify Incident ==\n'
curl -fsS -X POST "${BASE_URL}/api/attest/verify" -H 'Content-Type: application/json' -d "{\"incident_id\":\"${INCIDENT_ID}\"}" | jq

printf '\n== Live Stellar Config In Cluster ==\n'
kubectl exec -n default deployment/k8s-whisperer -- sh -lc 'printf "STELLAR_NETWORK=%s\n" "$STELLAR_NETWORK"; printf "STELLAR_RPC_URL=%s\n" "$STELLAR_RPC_URL"; printf "STELLAR_CONTRACT_ID=%s\n" "$STELLAR_CONTRACT_ID"'
