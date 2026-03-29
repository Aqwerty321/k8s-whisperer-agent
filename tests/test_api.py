import hashlib
import hmac
import json
import time

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


def _signed_headers(*, body: bytes, secret: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    base_string = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    signature = "v0=" + hmac.new(secret.encode("utf-8"), base_string, hashlib.sha256).hexdigest()
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
        "Content-Type": "application/x-www-form-urlencoded",
    }
