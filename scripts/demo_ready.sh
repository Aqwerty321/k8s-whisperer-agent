#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

bash "${ROOT_DIR}/scripts/deploy_backend.sh"
bash "${ROOT_DIR}/scripts/demo_reset.sh"
bash "${ROOT_DIR}/scripts/run_public_callback_bridge.sh"

for _ in {1..20}; do
  if curl -fsS "http://127.0.0.1:8010/health" >/dev/null 2>&1 && curl -fsS "https://slack.aqwerty321.me/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS "http://127.0.0.1:8010/health" >/dev/null

printf 'Demo environment is ready.\n'
printf 'Public health: %s\n' "$(curl -fsS https://slack.aqwerty321.me/health)"
