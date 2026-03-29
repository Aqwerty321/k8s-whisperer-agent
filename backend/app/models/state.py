from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict
from uuid import uuid4

Severity = Literal["low", "medium", "high", "critical"]
BlastRadius = Literal["low", "medium", "high"]
AnomalyType = Literal[
    "CrashLoopBackOff",
    "OOMKilled",
    "PendingPod",
    "ImagePullBackOff",
    "CPUThrottling",
    "EvictedPod",
    "DeploymentStalled",
    "NodeNotReady",
    "Unknown",
]
ActionType = Literal[
    "notify_only",
    "restart_pod",
    "delete_pod",
    "patch_pod",
    "collect_more_evidence",
    "escalate_to_human",
]


class Anomaly(TypedDict, total=False):
    anomaly_type: AnomalyType
    severity: Severity
    resource_kind: str
    resource_name: str
    namespace: str
    workload_kind: str
    workload_name: str
    summary: str
    confidence: float
    evidence: list[str]


class RemediationPlan(TypedDict, total=False):
    action: ActionType
    target_kind: str
    target_name: str
    namespace: str
    parameters: dict[str, Any]
    confidence: float
    blast_radius: BlastRadius
    reason: str
    requires_human: bool


class LogEntry(TypedDict, total=False):
    timestamp: str
    incident_id: str
    namespace: str
    anomaly_type: str
    decision: str
    action: str
    explanation: str
    diagnosis: str
    diagnosis_evidence: list[str]
    result: str
    tx_id: str | None


class WhisperState(TypedDict, total=False):
    incident_id: str
    created_at: str
    updated_at: str
    namespace: str
    cluster_state: dict[str, Any]
    events: list[dict[str, Any]]
    seeded_resource_names: list[str]
    anomalies: list[Anomaly]
    suppressed_anomalies: list[Anomaly]
    diagnosis: str
    diagnosis_evidence: list[str]
    plan: RemediationPlan | None
    approved: bool | None
    result: str
    audit_log: list[LogEntry]
    slack_channel: str | None
    slack_message_ts: str | None
    slack_prompt_sent: bool
    awaiting_human: bool
    error: str | None
    continuous_mode: bool
    explanation: str
    attestation_tx_id: str | None


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_incident_id() -> str:
    return f"incident-{uuid4().hex[:12]}"


def build_initial_state(
    *,
    namespace: str,
    slack_channel: str | None = None,
    continuous_mode: bool = False,
    incident_id: str | None = None,
    seed_events: list[dict[str, Any]] | None = None,
) -> WhisperState:
    normalized_seed_events = [
        {**event, "seeded": True}
        for event in (seed_events or [])
    ]
    return {
        "incident_id": incident_id or new_incident_id(),
        "created_at": current_timestamp(),
        "updated_at": current_timestamp(),
        "namespace": namespace,
        "cluster_state": {},
        "events": normalized_seed_events,
        "seeded_resource_names": [
            str(event.get("resource_name"))
            for event in normalized_seed_events
            if event.get("resource_name")
        ],
        "anomalies": [],
        "suppressed_anomalies": [],
        "diagnosis": "",
        "diagnosis_evidence": [],
        "plan": None,
        "approved": None,
        "result": "",
        "audit_log": [],
        "slack_channel": slack_channel,
        "slack_message_ts": None,
        "slack_prompt_sent": False,
        "awaiting_human": False,
        "error": None,
        "continuous_mode": continuous_mode,
        "explanation": "",
        "attestation_tx_id": None,
    }


def latest_anomaly(state: WhisperState) -> Anomaly | None:
    anomalies = state.get("anomalies", [])
    if not anomalies:
        return None
    return anomalies[0]
