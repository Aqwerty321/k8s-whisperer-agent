#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

kubectl delete pod -n default -l app=demo-oomkill --ignore-not-found
kubectl delete pod demo-pending -n default --ignore-not-found
kubectl delete deployment demo-crashloop -n default --ignore-not-found

kubectl rollout restart deployment/k8s-whisperer -n default
kubectl rollout status deployment/k8s-whisperer -n default

kubectl exec deployment/k8s-whisperer -n default -- sh -lc 'rm -f /app/runtime/audit/audit.jsonl /app/runtime/data/langgraph-checkpoints.pkl'
kubectl rollout restart deployment/k8s-whisperer -n default
kubectl rollout status deployment/k8s-whisperer -n default

bash "${ROOT_DIR}/scripts/deploy_demo.sh"

printf 'Demo runtime and workloads reset.\n'
