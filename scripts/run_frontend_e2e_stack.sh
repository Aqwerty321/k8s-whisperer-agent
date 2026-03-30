#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"

API_PORT="${API_PORT:-18010}"
API_TARGET_PORT="${API_TARGET_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-4173}"
API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-http://127.0.0.1:${API_PORT}}"

cleanup() {
  if [[ -n "${PF_PID:-}" ]]; then
    kill "${PF_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${VITE_PID:-}" ]]; then
    kill "${VITE_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

pkill -f "kubectl port-forward svc/k8s-whisperer -n default ${API_PORT}:${API_TARGET_PORT}" >/dev/null 2>&1 || true
pkill -f "vite --host 127.0.0.1 --port ${FRONTEND_PORT}" >/dev/null 2>&1 || true

kubectl port-forward svc/k8s-whisperer -n default "${API_PORT}:${API_TARGET_PORT}" >/tmp/k8swhisperer-api-forward.log 2>&1 &
PF_PID=$!

pushd "${FRONTEND_DIR}" >/dev/null
VITE_API_PROXY_TARGET="${API_PROXY_TARGET}" npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT}" >/tmp/k8swhisperer-frontend.log 2>&1 &
VITE_PID=$!
popd >/dev/null

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${FRONTEND_PORT}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

printf 'Frontend E2E stack ready.\n'
printf 'API: http://127.0.0.1:%s\n' "${API_PORT}"
printf 'Frontend: http://127.0.0.1:%s\n' "${FRONTEND_PORT}"

wait
