#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

wait_for_labeled_pod() {
  local label_selector="$1"
  local namespace="$2"
  for _ in {1..30}; do
    if kubectl get pods -n "${namespace}" -l "${label_selector}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null | grep -q .; then
      return 0
    fi
    sleep 1
  done
  printf 'Timed out waiting for a pod with selector %s in namespace %s\n' "${label_selector}" "${namespace}" >&2
  return 1
}

minikube ssh -- "sudo rm -rf /tmp/k8s-whisperer-demo-crashloop && sudo mkdir -p /tmp/k8s-whisperer-demo-crashloop"
kubectl delete deployment demo-crashloop -n default --ignore-not-found
kubectl delete deployment demo-oomkill -n default --ignore-not-found
kubectl delete pod demo-pending -n default --ignore-not-found

for deployment in demo-crashloop demo-oomkill; do
  if kubectl get deployment "${deployment}" -n default >/dev/null 2>&1; then
    kubectl wait --for=delete "deployment/${deployment}" -n default --timeout=60s
  fi
done

kubectl apply -f "${ROOT_DIR}/k8s/demo/crashloop.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/demo/oomkill.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/demo/pending.yaml"

wait_for_labeled_pod "app=demo-crashloop" default
wait_for_labeled_pod "app=demo-oomkill" default

for _ in {1..30}; do
  if kubectl get pod demo-pending -n default >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

kubectl get pod demo-pending -n default >/dev/null

printf 'Demo workloads deployed.\n'
