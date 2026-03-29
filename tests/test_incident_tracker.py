from backend.app.agent.incident_tracker import IncidentTracker


def test_incident_tracker_suppresses_open_duplicate() -> None:
    tracker = IncidentTracker(dedup_window_seconds=300)
    anomaly = {
        "anomaly_type": "CrashLoopBackOff",
        "resource_kind": "Pod",
        "resource_name": "demo",
        "namespace": "default",
    }

    filtered, suppressed = tracker.filter_anomalies(
        incident_id="incident-1",
        anomalies=[anomaly],
        deduplicate=True,
    )
    assert filtered == [anomaly]
    assert suppressed == []

    filtered, suppressed = tracker.filter_anomalies(
        incident_id="incident-2",
        anomalies=[anomaly],
        deduplicate=True,
    )
    assert filtered == []
    assert suppressed == [anomaly]
