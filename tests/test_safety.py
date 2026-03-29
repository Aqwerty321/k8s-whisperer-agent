from backend.app.agent.safety import hitl_route, is_auto_approvable, safety_route
from backend.app.models import build_initial_state


def test_auto_approve_low_blast_radius_plan() -> None:
    plan = {
        "action": "restart_pod",
        "blast_radius": "low",
        "confidence": 0.9,
        "requires_human": False,
    }
    assert is_auto_approvable(plan, threshold=0.8) is True


def test_block_medium_blast_radius_plan() -> None:
    plan = {
        "action": "restart_pod",
        "blast_radius": "medium",
        "confidence": 0.95,
        "requires_human": False,
    }
    assert is_auto_approvable(plan, threshold=0.8) is False


def test_safety_route_returns_hitl_when_not_safe() -> None:
    state = build_initial_state(namespace="default")
    state["plan"] = {
        "action": "escalate_to_human",
        "blast_radius": "high",
        "confidence": 0.4,
        "requires_human": True,
    }
    assert safety_route(state, threshold=0.8) == "hitl"


def test_hitl_route_respects_decision() -> None:
    state = build_initial_state(namespace="default")
    state["approved"] = True
    assert hitl_route(state) == "execute"

    state["approved"] = False
    assert hitl_route(state) == "explain_log"
