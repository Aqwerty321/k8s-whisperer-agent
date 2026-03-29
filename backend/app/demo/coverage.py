from __future__ import annotations

from typing import Any


def build_demo_coverage(
    *,
    incidents: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    oomkill_limit: str | None,
) -> dict[str, Any]:
    normalized_incidents = [_normalize_incident(incident) for incident in incidents]
    visible_incidents = [incident for incident in normalized_incidents if not _is_stale_rejected_noise(incident)]

    crashloop_auto = any(
        incident.get("anomaly_type") == "CrashLoopBackOff" and incident.get("status") == "completed"
        for incident in visible_incidents
    )
    oomkill_approved = any(
        incident.get("anomaly_type") == "OOMKilled"
        and incident.get("approved") is True
        and _is_successful_approved_oomkill_result(str(incident.get("result") or ""))
        for incident in visible_incidents
    )
    oomkill_rejected = any(
        incident.get("anomaly_type") == "OOMKilled"
        and incident.get("approved") is False
        and "Operator rejected remediation" in str(incident.get("result") or "")
        for incident in visible_incidents
    )
    pending_guidance = any(
        incident.get("anomaly_type") == "PendingPod"
        for incident in visible_incidents
    )
    awaiting_human = [incident for incident in visible_incidents if incident.get("status") == "awaiting_human"]

    covered = sum([crashloop_auto, oomkill_approved, oomkill_rejected, pending_guidance])
    readiness = "ready" if covered >= 3 and not awaiting_human else "in_progress"
    if not visible_incidents:
        readiness = "empty"

    return {
        "readiness": readiness,
        "covered_stories": {
            "crashloop_auto": crashloop_auto,
            "oomkill_approved": oomkill_approved,
            "oomkill_rejected": oomkill_rejected,
            "pending_guidance": pending_guidance,
        },
        "visible_incident_count": len(visible_incidents),
        "awaiting_human_count": len(awaiting_human),
        "stale_hidden_count": max(len(normalized_incidents) - len(visible_incidents), 0),
        "oomkill_limit": oomkill_limit,
        "recent_decisions": _decision_counts(audits),
        "visible_incidents": visible_incidents,
    }


def _decision_counts(audits: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in audits:
        decision = str(entry.get("decision") or "unknown")
        counts[decision] = counts.get(decision, 0) + 1
    return counts


def _is_stale_rejected_noise(incident: dict[str, Any]) -> bool:
    return (
        incident.get("approved") is False
        and incident.get("status") == "completed"
        and not str(incident.get("result") or "").strip()
    )


def _is_successful_approved_oomkill_result(result: str) -> bool:
    return (
        "Patch action requires human implementation" in result
        or "Patched Deployment" in result
    )


def _normalize_incident(incident: dict[str, Any]) -> dict[str, Any]:
    anomalies = incident.get("anomalies") or []
    first_anomaly = anomalies[0] if anomalies else {}
    plan = incident.get("plan") or {}
    return {
        "incident_id": incident.get("incident_id"),
        "status": incident.get("status"),
        "awaiting_human": incident.get("awaiting_human", False),
        "anomaly_type": incident.get("anomaly_type") or first_anomaly.get("anomaly_type"),
        "resource_name": incident.get("resource_name") or first_anomaly.get("resource_name"),
        "plan_action": incident.get("plan_action") or plan.get("action"),
        "approved": incident.get("approved"),
        "result": incident.get("result") or "",
    }
