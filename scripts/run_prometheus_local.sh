#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROMETHEUS_CONTAINER_NAME="k8s-whisperer-prometheus"
PROMETHEUS_CONFIG_PATH="${ROOT_DIR}/deploy/prometheus/prometheus.yml"

if ! command -v docker >/dev/null 2>&1; then
  printf 'docker is required to run the local Prometheus helper.\n' >&2
  exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
  printf 'kubectl is required to run the local Prometheus helper.\n' >&2
  exit 1
fi

if ! curl -fsS http://127.0.0.1:8001/api/ >/dev/null 2>&1; then
  kubectl proxy --port=8001 >/tmp/k8swhisperer-kubectl-proxy.log 2>&1 &
fi

for _ in {1..20}; do
  if curl -fsS http://127.0.0.1:8001/api/ >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS http://127.0.0.1:8001/api/ >/dev/null

if docker ps -a --format '{{.Names}}' | grep -qx "${PROMETHEUS_CONTAINER_NAME}"; then
  docker rm -f "${PROMETHEUS_CONTAINER_NAME}" >/dev/null
fi

docker run -d \
  --name "${PROMETHEUS_CONTAINER_NAME}" \
  --network host \
  -v "${PROMETHEUS_CONFIG_PATH}:/etc/prometheus/prometheus.yml:ro" \
  prom/prometheus >/dev/null

for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:9090/-/ready >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS http://127.0.0.1:9090/-/ready >/dev/null
printf 'Local Prometheus is ready on http://127.0.0.1:9090\n'
printf 'Try: curl -sS "http://127.0.0.1:9090/api/v1/query?query=container_cpu_usage_seconds_total{namespace=\"default\"}" | jq\n'
