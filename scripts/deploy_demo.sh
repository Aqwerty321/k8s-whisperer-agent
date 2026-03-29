#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

kubectl apply -f "${ROOT_DIR}/k8s/demo/crashloop.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/demo/oomkill.yaml"
kubectl apply -f "${ROOT_DIR}/k8s/demo/pending.yaml"

printf 'Demo workloads deployed.\n'
