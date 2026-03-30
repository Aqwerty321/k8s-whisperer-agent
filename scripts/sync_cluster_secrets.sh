#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${NAMESPACE:-default}"
SECRET_NAME="${SECRET_NAME:-k8s-whisperer-secrets}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "${ROOT_DIR}/.env"
  set +a
fi

existing_value() {
  local key="$1"
  kubectl get secret "${SECRET_NAME}" -n "${NAMESPACE}" -o jsonpath="{.data.${key}}" 2>/dev/null | base64 -d 2>/dev/null || true
}

pick_value() {
  local env_key="$1"
  local secret_key="$2"
  local env_value="${!env_key:-}"
  if [[ -n "${env_value}" ]]; then
    printf '%s' "${env_value}"
    return
  fi
  existing_value "${secret_key}"
}

SLACK_BOT_TOKEN_VALUE="$(pick_value SLACK_BOT_TOKEN slack_bot_token)"
SLACK_SIGNING_SECRET_VALUE="$(pick_value SLACK_SIGNING_SECRET slack_signing_secret)"
GEMINI_API_KEY_VALUE="$(pick_value GEMINI_API_KEY gemini_api_key)"
STELLAR_RPC_URL_VALUE="$(pick_value STELLAR_RPC_URL stellar_rpc_url)"
STELLAR_SECRET_KEY_VALUE="$(pick_value STELLAR_SECRET_KEY stellar_secret_key)"
STELLAR_CONTRACT_ID_VALUE="$(pick_value STELLAR_CONTRACT_ID stellar_contract_id)"

kubectl create secret generic "${SECRET_NAME}" \
  -n "${NAMESPACE}" \
  --from-literal=slack_bot_token="${SLACK_BOT_TOKEN_VALUE}" \
  --from-literal=slack_signing_secret="${SLACK_SIGNING_SECRET_VALUE}" \
  --from-literal=gemini_api_key="${GEMINI_API_KEY_VALUE}" \
  --from-literal=stellar_rpc_url="${STELLAR_RPC_URL_VALUE}" \
  --from-literal=stellar_secret_key="${STELLAR_SECRET_KEY_VALUE}" \
  --from-literal=stellar_contract_id="${STELLAR_CONTRACT_ID_VALUE}" \
  --dry-run=client -o yaml | kubectl apply -f -

printf 'Secret %s synced in namespace %s.\n' "${SECRET_NAME}" "${NAMESPACE}"
printf 'Resolved values: slack=%s signing=%s gemini=%s stellar_rpc=%s stellar_secret=%s stellar_contract=%s\n' \
  "$( [[ -n "${SLACK_BOT_TOKEN_VALUE}" ]] && printf set || printf empty )" \
  "$( [[ -n "${SLACK_SIGNING_SECRET_VALUE}" ]] && printf set || printf empty )" \
  "$( [[ -n "${GEMINI_API_KEY_VALUE}" ]] && printf set || printf empty )" \
  "$( [[ -n "${STELLAR_RPC_URL_VALUE}" ]] && printf set || printf empty )" \
  "$( [[ -n "${STELLAR_SECRET_KEY_VALUE}" ]] && printf set || printf empty )" \
  "$( [[ -n "${STELLAR_CONTRACT_ID_VALUE}" ]] && printf set || printf empty )"
