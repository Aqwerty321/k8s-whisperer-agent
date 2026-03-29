from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
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
    result = request.app.state.runtime.resume_incident(incident_id=incident_id, approved=approved)
    return {
        "ok": True,
        "incident_id": incident_id,
        "approved": approved,
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
