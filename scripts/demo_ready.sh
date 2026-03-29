#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

backend_ok=0
if curl -fsS "http://127.0.0.1:8010/health" >/dev/null 2>&1; then
  backend_ok=1
elif kubectl get deployment k8s-whisperer -n default >/dev/null 2>&1; then
  if kubectl get deployment k8s-whisperer -n default -o jsonpath='{.status.readyReplicas}' 2>/dev/null | grep -qx '1'; then
    backend_ok=1
  fi
fi

if [[ "${backend_ok}" != "1" ]]; then
  bash "${ROOT_DIR}/scripts/deploy_backend.sh"
fi

bash "${ROOT_DIR}/scripts/demo_reset.sh"

if ! curl -fsS "http://127.0.0.1:8010/health" >/dev/null 2>&1 || ! curl -fsS "https://slack.aqwerty321.me/health" >/dev/null 2>&1; then
  bash "${ROOT_DIR}/scripts/run_public_callback_bridge.sh"
fi

stable_public_checks=0
for _ in {1..30}; do
  local_ok=0
  public_ok=0
  if curl -fsS "http://127.0.0.1:8010/health" >/dev/null 2>&1; then
    local_ok=1
  fi
  if curl -fsS "https://slack.aqwerty321.me/health" >/dev/null 2>&1; then
    public_ok=1
  fi

  if [[ "${local_ok}" == "1" && "${public_ok}" == "1" ]]; then
    stable_public_checks=$((stable_public_checks + 1))
    if [[ "${stable_public_checks}" -ge 2 ]]; then
      break
    fi
  else
    stable_public_checks=0
  fi
  sleep 2
done

curl -fsS "http://127.0.0.1:8010/health" >/dev/null
curl -fsS "https://slack.aqwerty321.me/health" >/dev/null

printf 'Demo environment is ready.\n'
printf 'Public health: %s\n' "$(curl -fsS https://slack.aqwerty321.me/health)"
