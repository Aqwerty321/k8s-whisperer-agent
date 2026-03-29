from __future__ import annotations

from typing import Any

from .coverage import build_demo_coverage


def recommend_next_step(
    *,
    backend_healthy: bool,
    incidents: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    oomkill_limit: str | None,
) -> dict[str, str]:
    coverage = build_demo_coverage(
        incidents=incidents,
        audits=audits,
        oomkill_limit=oomkill_limit,
    )
    visible_incidents = coverage["visible_incidents"]

    if not backend_healthy:
        return {
            "state": "backend_unhealthy",
            "next_step": "make demo-ready",
            "backup_step": "make demo-snapshot",
            "why": "The local backend is not healthy enough for a live walkthrough.",
        }

    pending = next((incident for incident in visible_incidents if incident.get("status") == "awaiting_human"), None)
    if pending is not None:
        incident_id = str(pending.get("incident_id") or "unknown")
        anomaly_type = str(pending.get("anomaly_type") or "incident")
        if anomaly_type == "OOMKilled":
            return {
                "state": "awaiting_human",
                "next_step": f"Approve the newest Slack card for {incident_id}",
                "backup_step": f"bash scripts/approve_incident.sh {incident_id} approve",
                "why": "A human-gated OOMKilled incident is paused and ready to resume.",
            }
        return {
            "state": "awaiting_human",
            "next_step": f"Inspect pending incident {incident_id}",
            "backup_step": f"curl -sS http://127.0.0.1:8010/api/incidents/{incident_id} | jq",
            "why": "There is a pending incident waiting for operator attention.",
        }

    if oomkill_limit and oomkill_limit != "64Mi":
        return {
            "state": "oomkill_already_patched",
            "next_step": "make demo-reset-oomkill",
            "backup_step": "kubectl get deployment demo-oomkill -n default -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}'",
            "why": f"demo-oomkill is already patched to {oomkill_limit}, so reset it before showing the approved fix again.",
        }

    if not coverage["covered_stories"]["crashloop_auto"]:
        return {
            "state": "missing_crashloop_story",
            "next_step": "bash scripts/demo_incident.sh crashloop | jq",
            "backup_step": "make demo-snapshot",
            "why": "The recent view does not show a completed CrashLoopBackOff auto-remediation story.",
        }

    if not coverage["covered_stories"]["oomkill_approved"]:
        return {
            "state": "missing_approved_oomkill",
            "next_step": "bash scripts/demo_incident.sh oomkill | jq",
            "backup_step": "Approve the newest Slack card or run bash scripts/approve_incident.sh",
            "why": "The recent view does not show a successful approved OOMKilled Deployment patch.",
        }

    if not coverage["covered_stories"]["oomkill_rejected"]:
        return {
            "state": "missing_rejected_oomkill",
            "next_step": "bash scripts/demo_incident.sh oomkill | jq",
            "backup_step": "Reject the newest Slack card or run bash scripts/approve_incident.sh <incident-id> reject",
            "why": "The recent view does not show the rejected human-decision branch yet.",
        }

    if not coverage["covered_stories"]["pending_guidance"]:
        return {
            "state": "missing_pending_story",
            "next_step": "bash scripts/demo_incident.sh pending | jq",
            "backup_step": "make demo-snapshot",
            "why": "The recent view does not show the recommendation-only PendingPod path.",
        }

    if coverage["stale_hidden_count"] > 0 or len(visible_incidents) >= 5 or len(audits) >= 5:
        return {
            "state": "demo_noise_high",
            "next_step": "make demo-prune",
            "backup_step": "make demo-snapshot",
            "why": "The recent window is full, so prune older incidents before continuing.",
        }

    return {
        "state": "demo_ready",
        "next_step": "make demo-snapshot",
        "backup_step": "bash scripts/export_incident_report.sh",
        "why": "The core demo stories are already present in the recent window.",
    }
