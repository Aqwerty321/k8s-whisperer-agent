#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

eval "$(minikube docker-env)"
docker build -t k8s-whisperer:dev "${ROOT_DIR}"
kubectl apply -f "${ROOT_DIR}/k8s/rbac.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/backend.yaml"
kubectl rollout status deployment/k8s-whisperer -n default

printf 'Backend image built inside minikube and deployed.\n'
