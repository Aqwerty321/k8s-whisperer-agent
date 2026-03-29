#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8010}"
INCIDENTS_LIMIT="${INCIDENTS_LIMIT:-10}"
AUDIT_LIMIT="${AUDIT_LIMIT:-10}"

backend_healthy=0
if curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
  backend_healthy=1
fi

INCIDENTS_JSON="$(curl -fsS "${BASE_URL}/api/incidents?limit=${INCIDENTS_LIMIT}" 2>/dev/null || printf '{"incidents": [], "count": 0}')"
AUDIT_JSON="$(curl -fsS "${BASE_URL}/api/audit?limit=${AUDIT_LIMIT}" 2>/dev/null || printf '{"summaries": [], "count": 0}')"
OOMKILL_LIMIT="$(kubectl get deployment demo-oomkill -n default -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}' 2>/dev/null || true)"

BACKEND_HEALTHY="${backend_healthy}" INCIDENTS_JSON="${INCIDENTS_JSON}" AUDIT_JSON="${AUDIT_JSON}" OOMKILL_LIMIT="${OOMKILL_LIMIT}" \
  .venv/bin/python - <<'PY'
import json
import os

from backend.app.demo import recommend_next_step

backend_healthy = os.environ.get("BACKEND_HEALTHY") == "1"
incidents = json.loads(os.environ.get("INCIDENTS_JSON", "{}") or "{}").get("incidents", [])
audits = json.loads(os.environ.get("AUDIT_JSON", "{}") or "{}").get("summaries", [])
oomkill_limit = os.environ.get("OOMKILL_LIMIT") or None

decision = recommend_next_step(
    backend_healthy=backend_healthy,
    incidents=incidents,
    audits=audits,
    oomkill_limit=oomkill_limit,
)

print(f"State: {decision['state']}")
print(f"Recent incidents: {len(incidents)}")
print(f"Recent audit entries: {len(audits)}")
if oomkill_limit:
    print(f"demo-oomkill memory limit: {oomkill_limit}")
print("Suggested next step:")
print(decision["next_step"])
print("Why:")
print(decision["why"])
print("Backup:")
print(decision["backup_step"])
PY
