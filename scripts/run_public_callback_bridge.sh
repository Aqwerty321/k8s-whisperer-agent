#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_PATH="${ROOT_DIR}/deploy/cloudflared/config.yml"
TUNNEL_NAME="${TUNNEL_NAME:-k8swhisperer}"
NAMESPACE="${NAMESPACE:-default}"
SERVICE_NAME="${SERVICE_NAME:-k8s-whisperer}"
LOCAL_PORT="${LOCAL_PORT:-8010}"
REMOTE_PORT="${REMOTE_PORT:-8010}"
PORT_FORWARD_LOG="${PORT_FORWARD_LOG:-/tmp/k8swhisperer-port-forward-8010.log}"
TUNNEL_LOG="${TUNNEL_LOG:-/tmp/k8swhisperer-named-tunnel.log}"

if [[ ! -f "${CONFIG_PATH}" ]]; then
  printf 'Missing %s\n' "${CONFIG_PATH}"
  printf 'Copy deploy/cloudflared/config.template.yml to deploy/cloudflared/config.yml and fill in the tunnel ID first.\n'
  exit 1
fi

pkill -f "kubectl port-forward svc/${SERVICE_NAME} ${LOCAL_PORT}:${REMOTE_PORT} -n ${NAMESPACE}" || true
pkill -f "cloudflared tunnel --config ${CONFIG_PATH} run ${TUNNEL_NAME}" || true

nohup kubectl port-forward "svc/${SERVICE_NAME}" "${LOCAL_PORT}:${REMOTE_PORT}" -n "${NAMESPACE}" >"${PORT_FORWARD_LOG}" 2>&1 &

for _ in {1..20}; do
  if curl -fsS "http://127.0.0.1:${LOCAL_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS "http://127.0.0.1:${LOCAL_PORT}/health" >/dev/null

nohup cloudflared tunnel --config "${CONFIG_PATH}" run "${TUNNEL_NAME}" >"${TUNNEL_LOG}" 2>&1 &

printf 'Public callback bridge started.\n'
printf 'Local backend proxy: http://127.0.0.1:%s\n' "${LOCAL_PORT}"
printf 'Port-forward log: %s\n' "${PORT_FORWARD_LOG}"
printf 'Tunnel log: %s\n' "${TUNNEL_LOG}"
