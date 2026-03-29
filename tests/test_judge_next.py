from backend.app.demo import recommend_next_step


def test_recommend_next_step_prefers_demo_ready_when_backend_unhealthy() -> None:
    decision = recommend_next_step(
        backend_healthy=False,
        incidents=[],
        audits=[],
        oomkill_limit=None,
    )

    assert decision["next_step"] == "make demo-ready"


def test_recommend_next_step_prefers_pending_human_incident() -> None:
    decision = recommend_next_step(
        backend_healthy=True,
        incidents=[
            {
                "incident_id": "incident-1",
                "status": "awaiting_human",
                "anomaly_type": "OOMKilled",
            }
        ],
        audits=[],
        oomkill_limit="64Mi",
    )

    assert "incident-1" in decision["next_step"]
    assert "approve_incident.sh incident-1 approve" in decision["backup_step"]


def test_recommend_next_step_resets_patched_oomkill_before_repeat_demo() -> None:
    decision = recommend_next_step(
        backend_healthy=True,
        incidents=[],
        audits=[],
        oomkill_limit="96Mi",
    )

    assert decision["next_step"] == "make demo-reset-oomkill"


def test_recommend_next_step_points_to_pending_story_when_missing() -> None:
    decision = recommend_next_step(
        backend_healthy=True,
        incidents=[
            {
                "incident_id": "incident-1",
                "status": "completed",
                "anomaly_type": "CrashLoopBackOff",
            },
            {
                "incident_id": "incident-2",
                "status": "completed",
                "anomaly_type": "OOMKilled",
                "approved": True,
                "result": "Patch action requires human implementation. Recommendation: Increase memory.",
            },
            {
                "incident_id": "incident-3",
                "status": "completed",
                "anomaly_type": "OOMKilled",
                "approved": False,
                "result": "Operator rejected remediation. No cluster mutation was executed.",
            },
        ],
        audits=[{"decision": "approved"}, {"decision": "rejected"}],
        oomkill_limit="64Mi",
    )

    assert decision["next_step"] == "bash scripts/demo_incident.sh pending | jq"


def test_recommend_next_step_prunes_when_recent_window_is_full() -> None:
    incidents = [
        {
            "incident_id": f"incident-{index}",
            "status": "completed",
            "anomaly_type": "CrashLoopBackOff" if index == 0 else "PendingPod" if index == 4 else "OOMKilled",
            "approved": True if index == 1 else False if index == 2 else None,
            "result": (
                "Patch action requires human implementation. Recommendation: Increase memory."
                if index == 1
                else "Operator rejected remediation. No cluster mutation was executed."
                if index == 2
                else "ok"
            ),
        }
        for index in range(5)
    ]
    decision = recommend_next_step(
        backend_healthy=True,
        incidents=incidents,
        audits=[{"decision": "approved"}] * 5,
        oomkill_limit="64Mi",
    )

    assert decision["next_step"] == "make demo-prune"


def test_recommend_next_step_accepts_real_patched_oomkill_story_too() -> None:
    decision = recommend_next_step(
        backend_healthy=True,
        incidents=[
            {
                "incident_id": "incident-1",
                "status": "completed",
                "anomaly_type": "CrashLoopBackOff",
            },
            {
                "incident_id": "incident-2",
                "status": "completed",
                "anomaly_type": "OOMKilled",
                "approved": True,
                "result": "Patched Deployment default/demo-oomkill. Rollout: ok",
            },
            {
                "incident_id": "incident-3",
                "status": "completed",
                "anomaly_type": "OOMKilled",
                "approved": False,
                "result": "Operator rejected remediation. No cluster mutation was executed.",
            },
            {
                "incident_id": "incident-4",
                "status": "completed",
                "anomaly_type": "PendingPod",
                "result": "Recommendation recorded.",
            },
        ],
        audits=[{"decision": "approved"}, {"decision": "rejected"}],
        oomkill_limit="64Mi",
    )

    assert decision["next_step"] == "make demo-snapshot"
