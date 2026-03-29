#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

kubectl delete pod -n default -l app=demo-oomkill --ignore-not-found
kubectl delete pod demo-pending -n default --ignore-not-found
kubectl delete deployment demo-crashloop -n default --ignore-not-found

kubectl port-forward svc/k8s-whisperer 18010:8010 -n default >/tmp/k8swhisperer-demo-reset-port-forward.log 2>&1 &
PF_PID=$!
cleanup() {
  if kill -0 "${PF_PID}" >/dev/null 2>&1; then
    kill "${PF_PID}" >/dev/null 2>&1 || true
    wait "${PF_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

for _ in {1..20}; do
  if curl -fsS "http://127.0.0.1:18010/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS -X POST "http://127.0.0.1:18010/api/demo/reset" -H 'Content-Type: application/json' -d '{"clear_audit": true}' >/dev/null

bash "${ROOT_DIR}/scripts/deploy_demo.sh"

printf 'Demo runtime and workloads reset.\n'
