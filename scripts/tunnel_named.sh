#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_PATH="${ROOT_DIR}/deploy/cloudflared/config.yml"
TUNNEL_NAME="${1:-k8swhisperer}"

if [[ ! -f "${CONFIG_PATH}" ]]; then
  printf 'Missing %s\n' "${CONFIG_PATH}"
  printf 'Copy deploy/cloudflared/config.template.yml to deploy/cloudflared/config.yml and fill in the tunnel ID first.\n'
  exit 1
fi

cloudflared tunnel --config "${CONFIG_PATH}" run "${TUNNEL_NAME}"
