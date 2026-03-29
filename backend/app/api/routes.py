from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi import Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..attestation import StellarAttestor, hash_incident_record


class RunOnceRequest(BaseModel):
    namespace: str | None = None
    slack_channel: str | None = None
    seed_events: list[dict[str, Any]] = Field(default_factory=list)


class AttestationRequest(BaseModel):
    incident_id: str


class PollerToggleRequest(BaseModel):
    enabled: bool


class PruneDemoRequest(BaseModel):
    keep_incidents: int = Field(default=5, ge=0, le=50)
    keep_audit_entries: int = Field(default=5, ge=0, le=200)


router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "namespace": settings.k8s_namespace,
    }


@router.get("/api/status")
async def status(request: Request) -> dict[str, Any]:
    return {
        **request.app.state.runtime.get_status(),
        "poller": request.app.state.poller.get_status(),
    }


@router.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str, request: Request) -> dict[str, Any]:
    incident = request.app.state.runtime.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return incident


@router.get("/api/incidents")
async def list_incidents(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    status_filter: str | None = Query(default=None, alias="status"),
    anomaly_type: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    status = request.app.state.runtime.get_status()
    latest_incidents = list(status.get("latest_incidents", []))[-limit:]
    if status_filter:
        latest_incidents = [incident for incident in latest_incidents if incident.get("status") == status_filter]
    if anomaly_type:
        latest_incidents = [
            incident
            for incident in latest_incidents
            if ((incident.get("anomalies") or [{}])[0].get("anomaly_type") == anomaly_type)
        ]
    if search:
        needle = search.lower()
        latest_incidents = [
            incident
            for incident in latest_incidents
            if needle in json.dumps(incident, sort_keys=True).lower()
        ]
    incident_summaries = [_summarize_incident(incident) for incident in latest_incidents]
    return {
        "incidents": incident_summaries,
        "count": len(incident_summaries),
        "tracked_incidents": status.get("tracked_incidents", {}),
    }


@router.get("/api/incidents/{incident_id}/summary")
async def get_incident_summary(incident_id: str, request: Request) -> dict[str, Any]:
    incident = request.app.state.runtime.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    audit_entries = request.app.state.audit_logger.read_incident(incident_id)
    return {
        "incident": _summarize_incident(incident),
        "audit_count": len(audit_entries),
        "latest_audit": audit_entries[-1] if audit_entries else None,
    }


@router.get("/api/incidents/{incident_id}/report", response_class=PlainTextResponse)
async def get_incident_report(incident_id: str, request: Request) -> str:
    incident = request.app.state.runtime.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    audit_entries = request.app.state.audit_logger.read_incident(incident_id)
    return _render_incident_report(incident=incident, audit_entries=audit_entries)


@router.get("/api/audit")
async def get_audit_entries(
    request: Request,
    limit: int = Query(default=20, ge=1, le=500),
    incident_id: str | None = None,
    anomaly_type: str | None = None,
    decision: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    entries = request.app.state.audit_logger.query(
        limit=limit,
        incident_id=incident_id,
        anomaly_type=anomaly_type,
        decision=decision,
        search=search,
    )
    return {
        "entries": entries,
        "summaries": [
            {
                "incident_id": entry.get("incident_id"),
                "timestamp": entry.get("timestamp"),
                "anomaly_type": entry.get("anomaly_type"),
                "decision": entry.get("decision"),
                "action": entry.get("action"),
                "result": entry.get("result"),
            }
            for entry in entries
        ],
        "count": len(entries),
    }


@router.get("/api/audit/{incident_id}")
async def get_audit_entries_for_incident(incident_id: str, request: Request) -> dict[str, Any]:
    entries = request.app.state.audit_logger.read_incident(incident_id)
    return {"incident_id": incident_id, "entries": entries, "count": len(entries)}


@router.post("/api/incidents/run-once")
async def run_once(payload: RunOnceRequest, request: Request) -> dict[str, Any]:
    return request.app.state.runtime.run_once(
        namespace=payload.namespace,
        slack_channel=payload.slack_channel,
        seed_events=payload.seed_events,
    )


@router.post("/api/poller/run-once")
async def poller_run_once(request: Request) -> dict[str, Any]:
    return await request.app.state.poller.trigger_once()


@router.post("/api/poller")
async def toggle_poller(payload: PollerToggleRequest, request: Request) -> dict[str, Any]:
    poller = request.app.state.poller
    if payload.enabled:
        await poller.start()
    else:
        await poller.stop()
    return poller.get_status()


@router.post("/api/demo/prune")
async def prune_demo_state(payload: PruneDemoRequest, request: Request) -> dict[str, Any]:
    runtime_result = request.app.state.runtime.prune_runtime_state(keep_incidents=payload.keep_incidents)
    audit_result = request.app.state.audit_logger.prune_recent(payload.keep_audit_entries)
    return {
        **runtime_result,
        "audit": audit_result,
    }


@router.post("/api/slack/actions")
async def slack_actions(request: Request) -> dict[str, Any]:
    raw_body = await request.body()
    slack_client = request.app.state.slack_client

    if not slack_client.verify_request_signature(request.headers, raw_body):
        raise HTTPException(status_code=401, detail="Invalid Slack signature.")

    try:
        interaction = slack_client.parse_interaction_payload(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    incident_id = interaction["incident_id"]
    approved = interaction["approved"]
    interaction_message_ts = interaction.get("message_ts")
    existing = request.app.state.runtime.get_incident(incident_id)
    if existing and not existing.get("awaiting_human", False) and existing.get("approved") is not None:
        existing_anomaly = ((existing or {}).get("anomalies") or [{}])[0]
        duplicate_message_ts = interaction_message_ts or existing.get("slack_message_ts")
        if duplicate_message_ts:
            slack_client.update_message(
                channel=interaction["channel"],
                ts=duplicate_message_ts,
                text=slack_client.render_decision_text(
                    incident_id=incident_id,
                    approved=bool(existing.get("approved")),
                ),
                blocks=slack_client.render_status_blocks(
                    incident_id=incident_id,
                    title="K8sWhisperer incident already processed",
                    status=str(existing.get("status") or "completed"),
                    anomaly_summary=existing_anomaly.get("summary") if existing else None,
                    diagnosis=(existing or {}).get("diagnosis") if existing else None,
                    action=((existing or {}).get("plan") or {}).get("action") if existing else None,
                    result="Duplicate Slack callback ignored. Incident was already processed.",
                    timeline=[
                        "approval callback received from Slack",
                        "incident state restored from runtime/checkpoint",
                        "duplicate callback ignored",
                    ],
                ),
            )
        return {
            "ok": True,
            "incident_id": incident_id,
            "approved": existing.get("approved"),
            "duplicate": True,
            "channel": interaction["channel"],
            "result": existing,
        }

    slack_message_ts = (existing.get("slack_message_ts") if existing else None) or interaction_message_ts
    channel = interaction["channel"]
    existing_anomaly = ((existing or {}).get("anomalies") or [{}])[0]

    slack_client.update_message(
        channel=channel,
        ts=slack_message_ts,
        text=slack_client.render_decision_text(incident_id=incident_id, approved=approved),
        blocks=slack_client.render_status_blocks(
            incident_id=incident_id,
            title="K8sWhisperer approval decision received",
            status="approved" if approved else "rejected",
            anomaly_summary=existing_anomaly.get("summary") if existing else None,
            diagnosis=(existing or {}).get("diagnosis") if existing else None,
            action=((existing or {}).get("plan") or {}).get("action") if existing else None,
            result="Resuming incident graph after Slack decision.",
            timeline=[
                "approval callback received from Slack",
                "incident state restored from runtime/checkpoint",
                f"decision applied: {'approve' if approved else 'reject'}",
            ],
        ),
    )
    result = request.app.state.runtime.resume_incident(incident_id=incident_id, approved=approved)
    return {
        "ok": True,
        "incident_id": incident_id,
        "approved": approved,
        "channel": channel,
        "result": result,
    }


@router.post("/api/attest")
async def attest_incident(payload: AttestationRequest, request: Request) -> dict[str, Any]:
    incident = request.app.state.runtime.get_incident(payload.incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    settings = request.app.state.settings
    attestor = StellarAttestor(
        network=settings.stellar_network,
        secret_key=settings.stellar_secret_key,
        rpc_url=settings.stellar_rpc_url,
        contract_id=settings.stellar_contract_id,
    )
    incident_hash = hash_incident_record(incident)
    attestation = attestor.anchor_incident(
        incident_id=payload.incident_id,
        incident_hash=incident_hash,
    )
    return {
        "incident_id": payload.incident_id,
        "incident_hash": incident_hash,
        "attestation": attestation,
    }


def _summarize_incident(incident: dict[str, Any]) -> dict[str, Any]:
    anomalies = incident.get("anomalies") or []
    first_anomaly = anomalies[0] if anomalies else {}
    plan = incident.get("plan") or {}
    return {
        "incident_id": incident.get("incident_id"),
        "status": incident.get("status"),
        "namespace": incident.get("namespace"),
        "awaiting_human": incident.get("awaiting_human", False),
        "anomaly_type": first_anomaly.get("anomaly_type"),
        "resource_name": first_anomaly.get("resource_name"),
        "workload_kind": first_anomaly.get("workload_kind"),
        "workload_name": first_anomaly.get("workload_name"),
        "plan_action": plan.get("action"),
        "approved": incident.get("approved"),
        "slack_message_ts": incident.get("slack_message_ts"),
        "result": incident.get("result"),
    }


def _render_incident_report(*, incident: dict[str, Any], audit_entries: list[dict[str, Any]]) -> str:
    summary = _summarize_incident(incident)
    anomalies = incident.get("anomalies") or []
    first_anomaly = anomalies[0] if anomalies else {}
    plan = incident.get("plan") or {}
    recommendation = (plan.get("parameters") or {}).get("recommendation") if isinstance(plan.get("parameters"), dict) else None

    lines = [
        f"# Incident Report: {summary.get('incident_id')}",
        "",
        f"- Status: {summary.get('status')}",
        f"- Namespace: {summary.get('namespace')}",
        f"- Anomaly: {summary.get('anomaly_type') or 'Unknown'}",
        f"- Resource: {summary.get('resource_name') or 'Unknown'}",
        f"- Action: {summary.get('plan_action') or 'none'}",
        f"- Approved: {summary.get('approved')}",
        "",
        "## Summary",
        str(first_anomaly.get("summary") or "No summary recorded."),
        "",
        "## Diagnosis",
        str(incident.get("diagnosis") or "No diagnosis recorded."),
        "",
        "## Plan",
        f"- Target: {plan.get('target_name') or 'unknown'}",
        f"- Blast Radius: {plan.get('blast_radius') or 'unknown'}",
        f"- Requires Human: {plan.get('requires_human')}",
    ]
    if recommendation:
        lines.extend([f"- Recommendation: {recommendation}"])
    lines.extend([
        "",
        "## Result",
        str(incident.get("result") or "No result recorded."),
        "",
        "## Audit Entries",
    ])
    if audit_entries:
        for entry in audit_entries:
            lines.append(
                f"- {entry.get('timestamp')}: decision={entry.get('decision')} action={entry.get('action')} result={entry.get('result')}"
            )
    else:
        lines.append("- No audit entries recorded.")
    return "\n".join(lines)
