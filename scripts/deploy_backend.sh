#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
NAMESPACE="default"
LABEL_SELECTOR="app=k8s-whisperer"

show_rollout_debug() {
  kubectl get pods -n "${NAMESPACE}" -l "${LABEL_SELECTOR}" -o wide || true
  local newest_pod
  newest_pod="$(kubectl get pods -n "${NAMESPACE}" -l "${LABEL_SELECTOR}" --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null || true)"
  if [[ -n "${newest_pod}" ]]; then
    kubectl describe pod -n "${NAMESPACE}" "${newest_pod}" || true
    kubectl logs -n "${NAMESPACE}" "${newest_pod}" --previous || kubectl logs -n "${NAMESPACE}" "${newest_pod}" || true
  fi
}

eval "$(minikube docker-env)"
docker build -t k8s-whisperer:dev "${ROOT_DIR}"
kubectl apply -f "${ROOT_DIR}/k8s/rbac.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/backend.yaml"
kubectl rollout restart deployment/k8s-whisperer -n "${NAMESPACE}"
if ! kubectl rollout status deployment/k8s-whisperer -n "${NAMESPACE}" --timeout=180s; then
  printf 'Backend rollout failed; recent pod diagnostics follow.\n' >&2
  show_rollout_debug
  exit 1
fi

printf 'Backend image built inside minikube and deployed.\n'
