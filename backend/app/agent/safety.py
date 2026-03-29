from __future__ import annotations

from collections.abc import Mapping

from ..models import RemediationPlan, WhisperState

DESTRUCTIVE_DENYLIST = {"drain_node", "delete_namespace", "rollback_deployment", "patch_node"}


def is_auto_approvable(plan: RemediationPlan | None, threshold: float) -> bool:
    if not plan:
        return False

    action = str(plan.get("action", ""))
    blast_radius = str(plan.get("blast_radius", "high"))
    confidence = float(plan.get("confidence", 0.0))
    requires_human = bool(plan.get("requires_human", False))

    if requires_human:
        return False
    if action in DESTRUCTIVE_DENYLIST:
        return False
    if blast_radius != "low":
        return False
    return confidence >= threshold


def safety_route(state: WhisperState, threshold: float) -> str:
    return "execute" if is_auto_approvable(state.get("plan"), threshold) else "hitl"


def detect_route(state: WhisperState) -> str:
    if state.get("anomalies"):
        return "diagnose"
    return "end"


def hitl_route(state: WhisperState) -> str:
    return "execute" if state.get("approved") else "explain_log"


def safe_plan_summary(plan: Mapping[str, object] | None) -> str:
    if not plan:
        return "No remediation plan produced."
    return (
        f"action={plan.get('action')} target={plan.get('target_name')} "
        f"blast_radius={plan.get('blast_radius')} confidence={plan.get('confidence')}"
    )
