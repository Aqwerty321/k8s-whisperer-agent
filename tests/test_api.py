import hashlib
import hmac
import json
import time
from urllib.parse import quote_plus
from unittest.mock import Mock

from fastapi.testclient import TestClient

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
        client.app.state.runtime._latest_states["incident-hitl-1"] = {
            "incident_id": "incident-hitl-1",
            "slack_message_ts": "stub-approval-1",
        }
        response = client.post("/api/slack/actions", content=body, headers=headers)

    assert response.status_code == 200
    client.app.state.slack_client.update_message.assert_called_once()


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


def test_incident_list_supports_filters() -> None:
    with TestClient(app) as client:
        client.app.state.runtime._latest_states["incident-filter-1"] = {
            "incident_id": "incident-filter-1",
            "status": "awaiting_human",
            "namespace": "default",
            "awaiting_human": True,
            "anomalies": [{"anomaly_type": "OOMKilled", "resource_name": "demo-oomkill"}],
            "plan": {"action": "patch_pod"},
        }
        client.app.state.runtime._latest_states["incident-filter-2"] = {
            "incident_id": "incident-filter-2",
            "status": "completed",
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
        final_incident = client.get(f"/api/incidents/{incident_id}")
        assert final_incident.status_code == 200
        final_payload = final_incident.json()
        assert final_payload["status"] == "completed"
        assert final_payload["approved"] is True
        assert final_payload["slack_message_ts"] == "stub-message-ts"
        assert (
            "Patched Deployment default/demo-oomkill" in final_payload["result"]
            or "Patch action requires human implementation" in final_payload["result"]
        )

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
