#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

minikube ssh -- "sudo rm -rf /tmp/k8s-whisperer-demo-crashloop && sudo mkdir -p /tmp/k8s-whisperer-demo-crashloop"
kubectl delete deployment demo-crashloop -n default --ignore-not-found

kubectl apply -f "${ROOT_DIR}/k8s/demo/crashloop.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/demo/oomkill.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/demo/pending.yaml"
kubectl rollout status deployment/demo-crashloop -n default

printf 'Demo workloads deployed.\n'
