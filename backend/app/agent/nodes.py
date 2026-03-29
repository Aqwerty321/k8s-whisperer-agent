from __future__ import annotations

from dataclasses import dataclass

from langgraph.types import interrupt

from ..audit import AuditLogger
from ..config import Settings
from ..integrations.k8s import K8sClient
from ..integrations.llm import LLMClient
from ..integrations.prometheus import PrometheusClient
from ..integrations.slack import SlackClient
from ..models import LogEntry, WhisperState, current_timestamp, latest_anomaly
from .safety import is_auto_approvable


@dataclass(frozen=True)
class AgentDependencies:
    settings: Settings
    audit_logger: AuditLogger
    k8s_client: K8sClient
    llm_client: LLMClient
    prometheus_client: PrometheusClient
    slack_client: SlackClient


def make_observe_node(deps: AgentDependencies):
    def observe_node(state: WhisperState) -> WhisperState:
        namespace = state.get("namespace") or deps.settings.k8s_namespace
        snapshot = deps.k8s_client.get_cluster_snapshot(namespace)
        snapshot["prometheus"] = deps.prometheus_client.get_cpu_throttling(namespace=namespace)
        seeded_events = list(state.get("events", []))
        live_events = list(snapshot.get("events", []))
        combined_events = seeded_events + [event for event in live_events if event not in seeded_events]
        return {
            "namespace": namespace,
            "cluster_state": snapshot,
            "events": combined_events,
            "approved": state.get("approved"),
            "error": snapshot.get("error"),
        }

    return observe_node


def make_detect_node(deps: AgentDependencies):
    def detect_node(state: WhisperState) -> WhisperState:
        namespace = state.get("namespace") or deps.settings.k8s_namespace
        anomalies = deps.llm_client.classify_events(
            events=state.get("events", []),
            cluster_state=state.get("cluster_state", {}),
            namespace=namespace,
        )
        seeded_resource_names = {str(name) for name in state.get("seeded_resource_names", []) if name}
        if seeded_resource_names:
            filtered = [
                anomaly
                for anomaly in anomalies
                if str(anomaly.get("resource_name") or "") in seeded_resource_names
                or str(anomaly.get("workload_name") or "") in seeded_resource_names
            ]
            if filtered:
                anomalies = _prioritize_anomalies(filtered)
        else:
            anomalies = _prioritize_anomalies(anomalies)
        return {"anomalies": anomalies}

    return detect_node


def make_diagnose_node(deps: AgentDependencies):
    def diagnose_node(state: WhisperState) -> WhisperState:
        anomaly = latest_anomaly(state)
        if anomaly is None:
            return {"diagnosis": "No anomaly was available for diagnosis.", "diagnosis_evidence": []}

        namespace = anomaly.get("namespace") or state.get("namespace") or deps.settings.k8s_namespace
        resource_name = anomaly.get("resource_name", "unknown")
        resource_kind = str(anomaly.get("resource_kind") or "Pod")
        if resource_kind == "Node":
            logs = ""
            pod_description = deps.k8s_client.describe_node(name=resource_name)
        else:
            logs = deps.k8s_client.get_pod_logs(name=resource_name, namespace=namespace)
            pod_description = deps.k8s_client.describe_pod(name=resource_name, namespace=namespace)
        diagnosis = deps.llm_client.diagnose(
            anomaly=anomaly,
            logs=logs,
            pod_description=pod_description,
        )
        return {
            "diagnosis": diagnosis,
            "diagnosis_evidence": _build_diagnosis_evidence(anomaly=anomaly, logs=logs, pod_description=pod_description),
        }

    return diagnose_node


def make_plan_node(deps: AgentDependencies):
    def plan_node(state: WhisperState) -> WhisperState:
        anomaly = latest_anomaly(state)
        if anomaly is None:
            return {"plan": None}
        plan = deps.llm_client.plan_remediation(
            anomaly=anomaly,
            diagnosis=state.get("diagnosis", ""),
        )
        return {"plan": plan}

    return plan_node


def make_safety_gate_node(deps: AgentDependencies):
    def safety_gate_node(state: WhisperState) -> WhisperState:
        plan = state.get("plan")
        if not plan:
            return {"approved": False, "awaiting_human": False}

        auto_approved = is_auto_approvable(
            plan,
            threshold=deps.settings.auto_approve_threshold,
        )
        if auto_approved:
            return {"approved": True, "awaiting_human": False}
        return {"approved": None, "awaiting_human": True}

    return safety_gate_node


def make_hitl_node(deps: AgentDependencies):
    def notify_human_node(state: WhisperState) -> WhisperState:
        if state.get("slack_prompt_sent"):
            return {}

        plan = state.get("plan") or {}
        anomaly = latest_anomaly(state)
        summary = anomaly.get("summary", "Incident requires human review.") if anomaly else "Incident requires human review."
        slack_response = deps.slack_client.send_approval_request(
            channel=state.get("slack_channel") or deps.settings.slack_default_channel,
            incident_id=state["incident_id"],
            summary=summary,
            plan=plan,
        )
        return {
            "slack_channel": slack_response.get("channel") or state.get("slack_channel"),
            "slack_message_ts": slack_response.get("ts") or state.get("slack_message_ts"),
            "slack_prompt_sent": True,
        }

    def hitl_node(state: WhisperState) -> WhisperState:
        plan = state.get("plan") or {}
        anomaly = latest_anomaly(state)
        summary = anomaly.get("summary", "Incident requires human review.") if anomaly else "Incident requires human review."
        decision = interrupt(
            {
                "incident_id": state["incident_id"],
                "summary": summary,
                "plan": plan,
                "slack_response": {
                    "channel": state.get("slack_channel") or deps.settings.slack_default_channel,
                    "ts": state.get("slack_message_ts"),
                },
            }
        )
        approved = bool((decision or {}).get("approved"))
        return {
            "approved": approved,
            "awaiting_human": False,
            "slack_prompt_sent": True,
            "result": (
                state.get("result")
                if approved
                else "Operator rejected remediation. No cluster mutation was executed."
            ),
        }

    return notify_human_node, hitl_node


def make_execute_node(deps: AgentDependencies):
    def execute_node(state: WhisperState) -> WhisperState:
        plan = state.get("plan") or {}
        action = plan.get("action", "notify_only")
        target_name = str(plan.get("target_name") or "unknown")
        namespace = str(plan.get("namespace") or state.get("namespace") or deps.settings.k8s_namespace)

        if not state.get("approved") and bool(plan.get("requires_human")):
            return {"result": "Execution skipped because the remediation was not approved."}

        if action == "restart_pod":
            workload_kind = str(plan.get("parameters", {}).get("target_workload_kind") or "")
            workload_name = str(plan.get("parameters", {}).get("target_workload_name") or "")
            outcome = deps.k8s_client.delete_pod(name=target_name, namespace=namespace)
            verification = deps.k8s_client.verify_pod_recovery(
                name=target_name,
                namespace=namespace,
                workload_kind=workload_kind or None,
                workload_name=workload_name or None,
                timeout_seconds=deps.settings.verify_timeout_seconds,
            )
            result = (
                f"Restarted pod via delete request. Outcome: {outcome.get('message')}. "
                f"Verification: {verification.get('message')}"
            )
            if not outcome.get("ok"):
                return {"result": outcome.get("message", result), "error": outcome.get("message")}
            verification_message = str(verification.get("message") or "")
            if verification.get("recovered"):
                return {"result": result, "error": None}
            if verification.get("pod") is None and "not found" in verification_message.lower():
                return {
                    "result": (
                        "Restart request accepted. Original pod no longer exists and may have been "
                        "replaced already. Follow up on workload health if the issue persists."
                    ),
                    "error": None,
                }
            if not verification.get("recovered"):
                return {"result": result, "error": verification.get("message")}
            return {"result": result, "error": None}

        if action == "delete_pod":
            outcome = deps.k8s_client.delete_pod(name=target_name, namespace=namespace)
            verification = deps.k8s_client.verify_pod_recovery(
                name=target_name,
                namespace=namespace,
                expected_absent=True,
                timeout_seconds=deps.settings.verify_timeout_seconds,
            )
            result = (
                f"Delete request outcome: {outcome.get('message')}. "
                f"Verification: {verification.get('message')}"
            )
            if not outcome.get("ok"):
                return {"result": outcome.get("message", result), "error": outcome.get("message")}
            return {"result": result, "error": None if verification.get("recovered") else verification.get("message")}

        if action == "patch_pod":
            patch_body = plan.get("parameters", {}).get("patch")
            if isinstance(patch_body, dict):
                target_kind = str(plan.get("target_kind") or "Pod")
                workload_kind = str(plan.get("parameters", {}).get("target_workload_kind") or target_kind)
                workload_name = str(plan.get("parameters", {}).get("target_workload_name") or target_name)
                if workload_kind == "Deployment":
                    outcome = deps.k8s_client.patch_workload(
                        kind=workload_kind,
                        name=workload_name,
                        namespace=namespace,
                        patch=patch_body,
                    )
                    verification = deps.k8s_client.verify_workload_rollout(
                        kind=workload_kind,
                        name=workload_name,
                        namespace=namespace,
                        timeout_seconds=max(deps.settings.verify_timeout_seconds, 30),
                    )
                    result = (
                        f"Patched {workload_kind} {namespace}/{workload_name}. "
                        f"Rollout: {verification.get('message')}"
                    )
                    if not outcome.get("ok"):
                        return {
                            "result": outcome.get("message", result),
                            "error": outcome.get("message"),
                        }
                    if not verification.get("recovered"):
                        return {
                            "result": result,
                            "error": verification.get("message"),
                        }
                    return {
                        "result": result,
                        "error": None,
                    }
                else:
                    outcome = deps.k8s_client.patch_pod(
                        name=target_name,
                        namespace=namespace,
                        patch=patch_body,
                    )
                return {
                    "result": outcome.get("message", "Patch pod action completed."),
                    "error": None if outcome.get("ok") else outcome.get("message"),
                }

            recommendation = str(plan.get("parameters", {}).get("recommendation") or "Patch recommendation is required before execution.")
            return {
                "result": f"Patch action requires human implementation. Recommendation: {recommendation}",
                "error": None,
            }

        if action == "notify_only":
            return {
                "result": "No cluster mutation executed. Incident was summarized for operator review.",
                "error": None,
            }

        if action == "collect_more_evidence":
            return {
                "result": "No cluster mutation executed. Additional evidence collection is required.",
                "error": None,
            }

        if action == "escalate_to_human":
            return {
                "result": "Escalated to a human operator. No automated cluster mutation was executed.",
                "error": None,
            }

        return {"result": f"Action `{action}` is not implemented in the scaffold.", "error": None}

    return execute_node


def make_explain_log_node(deps: AgentDependencies):
    def explain_log_node(state: WhisperState) -> WhisperState:
        anomaly = latest_anomaly(state)
        explanation = deps.llm_client.explain(
            anomaly=anomaly,
            diagnosis=state.get("diagnosis", ""),
            plan=state.get("plan"),
            approved=state.get("approved"),
            result=state.get("result", ""),
        )
        entry: LogEntry = {
            "timestamp": current_timestamp(),
            "incident_id": state["incident_id"],
            "namespace": state.get("namespace", deps.settings.k8s_namespace),
            "anomaly_type": anomaly.get("anomaly_type", "Unknown") if anomaly else "Unknown",
            "decision": _decision_label(state),
            "action": (state.get("plan") or {}).get("action", "notify_only"),
            "explanation": explanation,
            "diagnosis": state.get("diagnosis", ""),
            "diagnosis_evidence": state.get("diagnosis_evidence", []),
            "result": state.get("result", ""),
            "tx_id": state.get("attestation_tx_id"),
        }
        deps.audit_logger.log(entry)
        slack_response = deps.slack_client.update_message(
            channel=state.get("slack_channel") or deps.settings.slack_default_channel,
            text=explanation,
            ts=state.get("slack_message_ts"),
            blocks=deps.slack_client.render_status_blocks(
                incident_id=state["incident_id"],
                title="K8sWhisperer incident update",
                status="completed" if not state.get("error") else "error",
                anomaly_summary=anomaly.get("summary") if anomaly else None,
                diagnosis=state.get("diagnosis", ""),
                action=(state.get("plan") or {}).get("action"),
                result=state.get("result", ""),
                timeline=_timeline_for_state(state),
            ),
        )
        return {
            "explanation": explanation,
            "audit_log": state.get("audit_log", []) + [entry],
            "slack_message_ts": slack_response.get("ts") or state.get("slack_message_ts"),
        }

    return explain_log_node


def _decision_label(state: WhisperState) -> str:
    plan = state.get("plan") or {}
    if state.get("approved") is True and bool(plan.get("requires_human")):
        return "approved"
    if state.get("approved") is False:
        return "rejected"
    if state.get("approved") is True:
        return "auto_approved"
    return "not_required_or_pending"


def _build_diagnosis_evidence(
    *,
    anomaly: dict[str, object],
    logs: str,
    pod_description: dict[str, object],
) -> list[str]:
    evidence = list(anomaly.get("evidence", [])) if isinstance(anomaly.get("evidence"), list) else []
    if logs and "Unable to fetch logs" not in logs:
        first_line = logs.strip().splitlines()[0] if logs.strip() else "logs collected"
        evidence.append(f"logs: {first_line[:200]}")
    node_snapshot = pod_description.get("node") if isinstance(pod_description.get("node"), dict) else None
    if node_snapshot:
        reason = node_snapshot.get("ready_reason") or "unknown"
        message = node_snapshot.get("ready_message") or ""
        entry = f"node Ready=False ({reason}): {message}".strip()
        if entry not in evidence:
            evidence.append(entry[:240])
    for event in pod_description.get("events", []) if isinstance(pod_description.get("events"), list) else []:
        if not isinstance(event, dict):
            continue
        reason = event.get("reason") or "event"
        message = event.get("message") or ""
        entry = f"event {reason}: {message}".strip()
        if entry not in evidence:
            evidence.append(entry[:240])
    return evidence[:10]


def _timeline_for_state(state: WhisperState) -> list[str]:
    plan = state.get("plan") or {}
    timeline = [
        "observe completed",
        "detect completed",
        "diagnose completed",
        f"plan generated: {plan.get('action', 'unknown')}",
    ]
    if state.get("approved") is True and bool(plan.get("requires_human")):
        timeline.append("human approval received")
    elif state.get("approved") is False:
        timeline.append("human approval rejected")
    elif state.get("approved") is True:
        timeline.append("auto-approved by safety gate")
    timeline.append(f"execution result: {state.get('result', 'pending')}")
    return timeline


def _prioritize_anomalies(anomalies: list[dict[str, object]]) -> list[dict[str, object]]:
    if not anomalies:
        return anomalies

    priority = {
        "NodeNotReady": 0,
        "OOMKilled": 1,
        "CrashLoopBackOff": 2,
        "PendingPod": 3,
        "CPUThrottling": 4,
        "ImagePullBackOff": 5,
        "EvictedPod": 6,
    }
    sorted_anomalies = sorted(
        anomalies,
        key=lambda anomaly: (
            priority.get(str(anomaly.get("anomaly_type") or "Unknown"), 99),
            0 if _has_workload_owner(anomaly) else 1,
            -float(anomaly.get("confidence") or 0.0),
        ),
    )
    return [sorted_anomalies[0]]


def _has_workload_owner(anomaly: dict[str, object]) -> bool:
    workload_kind = str(anomaly.get("workload_kind") or "")
    workload_name = str(anomaly.get("workload_name") or "")
    resource_name = str(anomaly.get("resource_name") or "")
    return bool(workload_kind and workload_kind != "Pod") or (workload_name and workload_name != resource_name)
