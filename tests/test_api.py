import hashlib
import hmac
import json
import time
from urllib.parse import quote_plus
from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.app.attestation import hash_incident_record
from backend.main import app


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_slack_action_requires_incident_id() -> None:
    body = b"payload=%7B%22actions%22%3A%5B%7B%22action_id%22%3A%22approve_incident%22%2C%22value%22%3A%22%7B%7D%22%7D%5D%7D"
    headers = _signed_headers(body=body, secret="test-secret")

    original_secret = app.state.settings.slack_signing_secret if hasattr(app.state, "settings") else None
    with TestClient(app) as client:
        client.app.state.slack_client.signing_secret = "test-secret"
        response = client.post("/api/slack/actions", data=body, headers=headers)

    if original_secret is not None:
        app.state.slack_client.signing_secret = original_secret
    assert response.status_code == 400
    assert response.json()["detail"] == "Slack action payload is missing incident_id."


def test_slack_action_rejects_bad_signature() -> None:
    payload = {
        "actions": [{"action_id": "approve_incident", "value": json.dumps({"incident_id": "incident-1"})}]
    }
    body = f"payload={json.dumps(payload)}".encode("utf-8")

    with TestClient(app) as client:
        client.app.state.slack_client.signing_secret = "test-secret"
        response = client.post(
            "/api/slack/actions",
            data=body,
            headers={
                "X-Slack-Request-Timestamp": str(int(time.time())),
                "X-Slack-Signature": "v0=invalid",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

    assert response.status_code == 401


def test_status_includes_poller_metadata() -> None:
    with TestClient(app) as client:
        response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.json()
    assert "poller" in payload
    assert "running" in payload["poller"]


def test_manual_poller_run_once_endpoint() -> None:
    with TestClient(app) as client:
        response = client.post("/api/poller/run-once")

    assert response.status_code == 200
    assert "incident_id" in response.json()


def test_audit_endpoints_return_entries() -> None:
    with TestClient(app) as client:
        client.app.state.audit_logger.log({
            "incident_id": "incident-audit-1",
            "timestamp": "2026-03-29T00:00:00Z",
            "result": "ok",
        })
        response = client.get("/api/audit?limit=5")
        incident_response = client.get("/api/audit/incident-audit-1")

    assert response.status_code == 200
    assert response.json()["count"] >= 1
    assert incident_response.status_code == 200
    assert incident_response.json()["incident_id"] == "incident-audit-1"
    assert incident_response.json()["count"] >= 1


def test_slack_action_updates_existing_incident_message() -> None:
    payload = {
        "channel": {"id": "C123"},
        "actions": [{"action_id": "approve_incident", "value": json.dumps({"incident_id": "incident-hitl-1"})}],
    }
    body = f"payload={quote_plus(json.dumps(payload))}".encode("utf-8")
    headers = _signed_headers(body=body, secret="test-secret")

    with TestClient(app) as client:
        client.app.state.slack_client.signing_secret = "test-secret"
        client.app.state.slack_client.update_message = Mock(return_value={"ok": True, "ts": "stub-approval-1"})
        client.app.state.runtime.resume_incident = Mock(return_value={"incident_id": "incident-hitl-1", "status": "completed"})
        client.app.state.runtime._latest_states["incident-hitl-1"] = {
            "incident_id": "incident-hitl-1",
            "slack_message_ts": "stub-approval-1",
            "awaiting_human": True,
        }
        response = client.post("/api/slack/actions", content=body, headers=headers)

    assert response.status_code == 200
    client.app.state.slack_client.update_message.assert_called_once()
    client.app.state.runtime.resume_incident.assert_called_once_with(incident_id="incident-hitl-1", approved=True)


def test_slack_action_is_idempotent_after_incident_completion() -> None:
    payload = {
        "channel": {"id": "C123"},
        "container": {"message_ts": "clicked-message-ts"},
        "actions": [{"action_id": "approve_incident", "value": json.dumps({"incident_id": "incident-complete-1"})}],
    }
    body = f"payload={quote_plus(json.dumps(payload))}".encode("utf-8")
    headers = _signed_headers(body=body, secret="test-secret")

    with TestClient(app) as client:
        client.app.state.slack_client.signing_secret = "test-secret"
        client.app.state.slack_client.update_message = Mock(return_value={"ok": True, "ts": "stub-complete-1"})
        existing_incident = {
            "incident_id": "incident-complete-1",
            "awaiting_human": False,
            "approved": True,
            "status": "completed",
            "slack_message_ts": "stub-complete-1",
        }
        client.app.state.runtime.get_incident = Mock(return_value=existing_incident)
        response = client.post("/api/slack/actions", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["duplicate"] is True
    client.app.state.slack_client.update_message.assert_called_once()


def test_incident_summary_endpoints_return_combined_views() -> None:
    with TestClient(app) as client:
        client.app.state.runtime._latest_states["incident-summary-1"] = {
            "incident_id": "incident-summary-1",
            "status": "completed",
            "namespace": "default",
            "awaiting_human": False,
            "anomalies": [
                {
                    "anomaly_type": "CrashLoopBackOff",
                    "resource_name": "demo",
                    "workload_kind": "Deployment",
                    "workload_name": "demo-api",
                }
            ],
            "plan": {"action": "restart_pod"},
            "approved": True,
            "result": "ok",
            "slack_message_ts": "stub-1",
        }
        client.app.state.audit_logger.log(
            {
                "incident_id": "incident-summary-1",
                "timestamp": "2026-03-29T00:00:00Z",
                "anomaly_type": "CrashLoopBackOff",
                "action": "restart_pod",
                "decision": "auto_approved",
                "result": "ok",
            }
        )

        list_response = client.get("/api/incidents")
        summary_response = client.get("/api/incidents/incident-summary-1/summary")

    assert list_response.status_code == 200
    assert summary_response.status_code == 200
    assert list_response.json()["count"] >= 1
    assert summary_response.json()["incident"]["incident_id"] == "incident-summary-1"
    assert summary_response.json()["audit_count"] >= 1


def test_incident_report_endpoint_returns_markdown() -> None:
    with TestClient(app) as client:
        client.app.state.runtime._latest_states["incident-report-1"] = {
            "incident_id": "incident-report-1",
            "status": "completed",
            "namespace": "default",
            "awaiting_human": False,
            "approved": False,
            "diagnosis": "Operator chose not to proceed.",
            "result": "Operator rejected remediation. No cluster mutation was executed.",
            "anomalies": [
                {
                    "anomaly_type": "OOMKilled",
                    "resource_name": "demo-oomkill",
                    "summary": "Container was OOMKilled after hitting memory limit",
                }
            ],
            "plan": {
                "action": "patch_pod",
                "target_name": "demo-oomkill",
                "blast_radius": "medium",
                "requires_human": True,
                "parameters": {"recommendation": "Increase memory."},
            },
        }
        client.app.state.audit_logger.log(
            {
                "incident_id": "incident-report-1",
                "timestamp": "2026-03-29T00:00:00Z",
                "decision": "rejected",
                "action": "patch_pod",
                "result": "Operator rejected remediation. No cluster mutation was executed.",
            }
        )

        response = client.get("/api/incidents/incident-report-1/report")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# Incident Report: incident-report-1" in response.text
    assert "## Result" in response.text
    assert "Operator rejected remediation" in response.text


def test_attest_endpoint_uses_runtime_incident_when_available() -> None:
    with TestClient(app) as client:
        client.app.state.runtime._latest_states["incident-attest-1"] = {
            "incident_id": "incident-attest-1",
            "status": "completed",
            "namespace": "default",
            "awaiting_human": False,
            "approved": True,
            "diagnosis": "CrashLoop recovered after restart.",
            "diagnosis_evidence": ["logs: crashloop recovered"],
            "result": "Restarted pod and verified recovery.",
            "updated_at": "2026-03-30T00:00:00Z",
            "anomalies": [
                {
                    "anomaly_type": "CrashLoopBackOff",
                    "resource_name": "demo-crashloop",
                    "summary": "Pod is crashlooping.",
                }
            ],
            "plan": {
                "action": "restart_pod",
            },
        }

        response = client.post("/api/attest", json={"incident_id": "incident-attest-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["incident_id"] == "incident-attest-1"
    assert payload["source"] == "runtime"
    assert payload["record"]["incident_id"] == "incident-attest-1"
    assert payload["record"]["anomaly"]["anomaly_type"] == "CrashLoopBackOff"
    assert payload["contract_key"].startswith("incident_")
    assert "attestation" in payload


def test_attest_endpoint_falls_back_to_audit_record() -> None:
    with TestClient(app) as client:
        client.app.state.runtime._latest_states.pop("incident-attest-audit-1", None)
        client.app.state.audit_logger.log(
            {
                "incident_id": "incident-attest-audit-1",
                "timestamp": "2026-03-30T00:00:00Z",
                "namespace": "default",
                "anomaly_type": "OOMKilled",
                "decision": "approved",
                "action": "patch_pod",
                "diagnosis": "Container exceeded memory limit.",
                "diagnosis_evidence": ["event OOMKilled"],
                "explanation": "Approved recommendation for more memory.",
                "result": "Recorded recommendation only.",
            }
        )

        response = client.post("/api/attest", json={"incident_id": "incident-attest-audit-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "audit"
    assert payload["record"]["incident_id"] == "incident-attest-audit-1"
    assert payload["record"]["anomaly"]["anomaly_type"] == "OOMKilled"
    assert "attestation" in payload


def test_attest_verify_endpoint_uses_persisted_tx_id_from_audit() -> None:
    with TestClient(app) as client:
        client.app.state.runtime._latest_states.pop("incident-attest-verify-1", None)
        client.app.state.audit_logger.log(
            {
                "incident_id": "incident-attest-verify-1",
                "timestamp": "2026-03-30T00:00:00Z",
                "namespace": "default",
                "anomaly_type": "OOMKilled",
                "decision": "approved",
                "action": "patch_pod",
                "diagnosis": "Container exceeded memory limit.",
                "diagnosis_evidence": ["event OOMKilled"],
                "explanation": "Approved recommendation for more memory.",
                "result": "Recorded recommendation only.",
                "tx_id": "stellar-tx-123",
            }
        )

        response = client.post("/api/attest/verify", json={"incident_id": "incident-attest-verify-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "audit"
    assert payload["verification"]["tx_id"] == "stellar-tx-123"
    if payload["verification"].get("stub"):
        assert payload["verification"]["verified"] is False
    else:
        assert payload["verification"]["verified"] is True


def test_attestation_hash_is_stable_after_tx_persistence() -> None:
    with TestClient(app) as client:
        incident = {
            "incident_id": "incident-stable-hash-1",
            "status": "completed",
            "namespace": "default",
            "awaiting_human": False,
            "approved": True,
            "diagnosis": "CrashLoop recovered after restart.",
            "diagnosis_evidence": ["logs: crashloop recovered"],
            "result": "Restarted pod and verified recovery.",
            "updated_at": "2026-03-30T00:00:00Z",
            "anomalies": [
                {
                    "anomaly_type": "CrashLoopBackOff",
                    "resource_kind": "Pod",
                    "resource_name": "demo-crashloop",
                    "workload_kind": "Deployment",
                    "workload_name": "demo-crashloop",
                    "summary": "Pod is crashlooping.",
                }
            ],
            "plan": {
                "action": "restart_pod",
                "target_kind": "Pod",
                "target_name": "demo-crashloop",
                "blast_radius": "low",
                "requires_human": False,
            },
        }
        client.app.state.runtime._latest_states[incident["incident_id"]] = incident

        first = client.post("/api/attest", json={"incident_id": incident["incident_id"]}).json()
        record = dict(first["record"])
        first_hash = hash_incident_record(record)

        client.app.state.runtime._latest_states[incident["incident_id"]]["attestation_tx_id"] = "stellar-tx-123"
        client.app.state.audit_logger.log(
            {
                "incident_id": incident["incident_id"],
                "timestamp": "2026-03-30T00:00:00Z",
                "namespace": "default",
                "anomaly_type": "CrashLoopBackOff",
                "decision": "attested",
                "action": "anchor_incident",
                "result": "Recorded attestation transaction stellar-tx-123.",
                "tx_id": "stellar-tx-123",
            }
        )

        second = client.post("/api/attest/verify", json={"incident_id": incident["incident_id"]}).json()
        second_hash = hash_incident_record(second["record"])

    assert first_hash == second_hash


def test_incident_list_supports_filters() -> None:
    with TestClient(app) as client:
        client.app.state.runtime._latest_states["incident-filter-1"] = {
            "incident_id": "incident-filter-1",
            "status": "awaiting_human",
            "created_at": "2026-03-29T00:00:01Z",
            "updated_at": "2026-03-29T00:00:01Z",
            "namespace": "default",
            "awaiting_human": True,
            "anomalies": [{"anomaly_type": "OOMKilled", "resource_name": "demo-oomkill"}],
            "plan": {"action": "patch_pod"},
        }
        client.app.state.runtime._latest_states["incident-filter-2"] = {
            "incident_id": "incident-filter-2",
            "status": "completed",
            "created_at": "2026-03-29T00:00:00Z",
            "updated_at": "2026-03-29T00:00:00Z",
            "namespace": "default",
            "awaiting_human": False,
            "anomalies": [{"anomaly_type": "CrashLoopBackOff", "resource_name": "demo-crashloop"}],
            "plan": {"action": "restart_pod"},
        }

        response = client.get("/api/incidents?status=awaiting_human&anomaly_type=OOMKilled")

    assert response.status_code == 200
    assert response.json()["count"] >= 1
    assert all(item["anomaly_type"] == "OOMKilled" for item in response.json()["incidents"])


def test_audit_endpoint_supports_search_filters() -> None:
    with TestClient(app) as client:
        client.app.state.audit_logger.log(
            {
                "incident_id": "incident-audit-search-1",
                "timestamp": "2026-03-29T00:00:00Z",
                "anomaly_type": "OOMKilled",
                "decision": "approved",
                "action": "patch_pod",
                "result": "manual patch required",
            }
        )
        response = client.get("/api/audit?anomaly_type=OOMKilled&decision=approved&search=manual")

    assert response.status_code == 200
    assert response.json()["count"] >= 1


def test_demo_prune_endpoint_trims_runtime_and_audit_state() -> None:
    with TestClient(app) as client:
        for index in range(4):
            client.app.state.runtime._latest_states[f"incident-prune-{index}"] = {
                "incident_id": f"incident-prune-{index}",
                "status": "completed",
                "created_at": f"2026-03-29T00:00:0{index}Z",
                "updated_at": f"2026-03-29T00:00:0{index}Z",
            }
            client.app.state.audit_logger.log(
                {
                    "incident_id": f"incident-prune-{index}",
                    "timestamp": f"2026-03-29T00:00:0{index}Z",
                    "decision": "approved",
                    "action": "patch_pod",
                    "result": "ok",
                }
            )

        response = client.post("/api/demo/prune", json={"keep_incidents": 2, "keep_audit_entries": 2})

    assert response.status_code == 200
    assert response.json()["remaining_incidents"] == 2
    assert response.json()["audit"]["kept"] == 2


def test_demo_reset_endpoint_clears_runtime_and_audit_state() -> None:
    with TestClient(app) as client:
        client.app.state.runtime._latest_states["incident-reset-1"] = {
            "incident_id": "incident-reset-1",
            "status": "awaiting_human",
            "created_at": "2026-03-29T00:00:00Z",
            "updated_at": "2026-03-29T00:00:00Z",
            "awaiting_human": True,
        }
        client.app.state.runtime._pending_incidents.add("incident-reset-1")
        client.app.state.runtime.checkpointer.put(
            {"configurable": {"thread_id": "incident-reset-1", "checkpoint_ns": ""}},
            {"id": "checkpoint-reset-1", "channel_values": {}, "channel_versions": {}, "versions_seen": {}, "pending_sends": []},
            {},
            {},
        )
        client.app.state.audit_logger.log(
            {
                "incident_id": "incident-reset-1",
                "timestamp": "2026-03-29T00:00:00Z",
                "decision": "approved",
                "action": "patch_pod",
                "result": "ok",
            }
        )

        response = client.post("/api/demo/reset", json={"clear_audit": True})

    assert response.status_code == 200
    assert response.json()["cleared_incidents"] >= 1
    assert response.json()["cleared_pending_incidents"] >= 1
    assert response.json()["cleared_checkpoints"] >= 1
    assert response.json()["audit"]["kept"] == 0
    assert app.state.runtime.get_status()["latest_incidents"] == []
    assert app.state.audit_logger.read_all() == []


def test_simulated_slack_workflow_end_to_end() -> None:
    with TestClient(app) as client:
        client.app.state.slack_client.signing_secret = "test-secret"
        response = client.post(
            "/api/incidents/run-once",
            json={
                "namespace": "default",
                "seed_events": [
                    {
                        "type": "Warning",
                        "reason": "OOMKilled",
                        "message": "Container was OOMKilled after hitting memory limit",
                        "namespace": "default",
                        "resource_name": "demo-oomkill",
                        "resource_kind": "Pod",
                    }
                ],
            },
        )

        assert response.status_code == 200
        initial = response.json()
        assert initial["status"] == "awaiting_human"
        assert initial["slack_message_ts"] == "stub-message-ts"
        incident_id = initial["incident_id"]

        callback_payload = {
            "channel": {"id": "C123"},
            "actions": [{"action_id": "approve_incident", "value": json.dumps({"incident_id": incident_id})}],
        }
        body = f"payload={quote_plus(json.dumps(callback_payload))}".encode("utf-8")
        callback_response = client.post(
            "/api/slack/actions",
            content=body,
            headers=_signed_headers(body=body, secret="test-secret"),
        )

        assert callback_response.status_code == 200
        assert callback_response.json()["accepted"] is True
        final_incident = client.get(f"/api/incidents/{incident_id}")
        assert final_incident.status_code == 200
        final_payload = final_incident.json()
        assert final_payload["status"] == "completed"
        assert final_payload["approved"] is True
        assert final_payload["slack_message_ts"] == "stub-message-ts"
        assert "Patch action requires human implementation" in final_payload["result"]

        audit_response = client.get(f"/api/audit/{incident_id}")
        assert audit_response.status_code == 200
        assert audit_response.json()["count"] >= 1


def _signed_headers(*, body: bytes, secret: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    base_string = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    signature = "v0=" + hmac.new(secret.encode("utf-8"), base_string, hashlib.sha256).hexdigest()
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
        "Content-Type": "application/x-www-form-urlencoded",
    }
