#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

minikube start
kubectl apply -f "${ROOT_DIR}/k8s/rbac.yaml"

printf 'minikube is running and RBAC has been applied.\n'
