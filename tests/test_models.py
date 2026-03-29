from backend.app.models import build_initial_state, latest_anomaly


def test_build_initial_state_has_expected_defaults() -> None:
    state = build_initial_state(namespace="default")

    assert state["namespace"] == "default"
    assert state["anomalies"] == []
    assert state["plan"] is None
    assert state["approved"] is None
    assert state["awaiting_human"] is False
    assert state["incident_id"].startswith("incident-")


def test_latest_anomaly_returns_first_item() -> None:
    state = build_initial_state(namespace="default")
    state["anomalies"] = [
        {
            "anomaly_type": "CrashLoopBackOff",
            "severity": "high",
            "resource_kind": "Pod",
            "resource_name": "demo",
            "namespace": "default",
            "summary": "demo crash looping",
            "confidence": 0.9,
            "evidence": ["restart count high"],
        }
    ]

    anomaly = latest_anomaly(state)
    assert anomaly is not None
    assert anomaly["resource_name"] == "demo"
