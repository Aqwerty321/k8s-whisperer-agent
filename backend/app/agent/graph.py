from __future__ import annotations

from threading import Lock
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from ..audit import AuditLogger
from ..config import Settings
from ..integrations.k8s import K8sClient
from ..integrations.llm import LLMClient
from ..integrations.prometheus import PrometheusClient
from ..integrations.slack import SlackClient
from ..models import WhisperState, build_initial_state, current_timestamp
from .checkpointer import PersistentInMemorySaver
from .incident_tracker import IncidentTracker
from .nodes import (
    AgentDependencies,
    make_detect_node,
    make_diagnose_node,
    make_execute_node,
    make_explain_log_node,
    make_hitl_node,
    make_observe_node,
    make_plan_node,
    make_safety_gate_node,
)
from .safety import detect_route, hitl_route, safety_route


def build_graph(deps: AgentDependencies, checkpointer: PersistentInMemorySaver):
    builder = StateGraph(WhisperState)
    builder.add_node("observe", make_observe_node(deps))
    builder.add_node("detect", make_detect_node(deps))
    builder.add_node("diagnose", make_diagnose_node(deps))
    builder.add_node("plan", make_plan_node(deps))
    builder.add_node("safety_gate", make_safety_gate_node(deps))
    notify_human_node, hitl_node = make_hitl_node(deps)
    builder.add_node("notify_human", notify_human_node)
    builder.add_node("hitl", hitl_node)
    builder.add_node("execute", make_execute_node(deps))
    builder.add_node("explain_log", make_explain_log_node(deps))

    builder.add_edge(START, "observe")
    builder.add_edge("observe", "detect")
    builder.add_conditional_edges("detect", detect_route, {"diagnose": "diagnose", "end": END})
    builder.add_edge("diagnose", "plan")
    builder.add_edge("plan", "safety_gate")
    builder.add_conditional_edges(
        "safety_gate",
        lambda state: safety_route(state, deps.settings.auto_approve_threshold),
        {"execute": "execute", "hitl": "notify_human"},
    )
    builder.add_edge("notify_human", "hitl")
    builder.add_conditional_edges("hitl", hitl_route, {"execute": "execute", "explain_log": "explain_log"})
    builder.add_edge("execute", "explain_log")
    builder.add_edge("explain_log", END)
    return builder.compile(checkpointer=checkpointer)


class AgentRuntime:
    def __init__(
        self,
        *,
        settings: Settings,
        audit_logger: AuditLogger,
        k8s_client: K8sClient,
        llm_client: LLMClient,
        prometheus_client: PrometheusClient,
        slack_client: SlackClient,
    ) -> None:
        self.deps = AgentDependencies(
            settings=settings,
            audit_logger=audit_logger,
            k8s_client=k8s_client,
            llm_client=llm_client,
            prometheus_client=prometheus_client,
            slack_client=slack_client,
        )
        self.checkpointer = PersistentInMemorySaver(settings.checkpoint_store_path)
        self.graph = build_graph(self.deps, self.checkpointer)
        self.incident_tracker = IncidentTracker(dedup_window_seconds=settings.incident_dedup_window_seconds)
        self._lock = Lock()
        self._latest_states: dict[str, dict[str, Any]] = {}
        self._pending_incidents: set[str] = set()
        self._hydrate_from_checkpoints()

    def run_once(
        self,
        *,
        namespace: str | None = None,
        slack_channel: str | None = None,
        seed_events: list[dict[str, Any]] | None = None,
        deduplicate: bool = False,
    ) -> dict[str, Any]:
        initial_state = build_initial_state(
            namespace=namespace or self.deps.settings.k8s_namespace,
            slack_channel=slack_channel or self.deps.settings.slack_default_channel,
            seed_events=seed_events,
        )
        return self._invoke_with_config(initial_state=initial_state, deduplicate=deduplicate)

    def resume_incident(self, *, incident_id: str, approved: bool) -> dict[str, Any]:
        config = {"configurable": {"thread_id": incident_id}}
        result = self.graph.invoke(Command(resume={"approved": approved}), config=config)
        normalized = self._normalize_result(result=result, incident_id=incident_id, config=config)
        normalized["updated_at"] = current_timestamp()
        with self._lock:
            self._latest_states[incident_id] = normalized
            self._pending_incidents.discard(incident_id)
        self.incident_tracker.hydrate_incident(normalized)
        return normalized

    def get_status(self) -> dict[str, Any]:
        self._hydrate_from_checkpoints()
        with self._lock:
            latest_incidents = sorted(
                self._latest_states.values(),
                key=lambda incident: str(incident.get("updated_at") or incident.get("created_at") or ""),
                reverse=True,
            )
            return {
                "pending_incidents": sorted(self._pending_incidents),
                "latest_incidents": latest_incidents[:10],
                "checkpoint_threads": self.checkpointer.list_threads(),
                "tracked_incidents": self.incident_tracker.snapshot(),
            }

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        snapshot = self._read_checkpoint_state(incident_id)
        if snapshot is not None:
            normalized = self._snapshot_to_incident(snapshot=snapshot, incident_id=incident_id)
            with self._lock:
                self._latest_states[incident_id] = normalized
                if normalized.get("awaiting_human"):
                    self._pending_incidents.add(incident_id)
                else:
                    self._pending_incidents.discard(incident_id)
            self.incident_tracker.hydrate_incident(normalized)
        with self._lock:
            return self._latest_states.get(incident_id)

    def _invoke_with_config(self, *, initial_state: WhisperState, deduplicate: bool) -> dict[str, Any]:
        incident_id = initial_state["incident_id"]
        config = {"configurable": {"thread_id": incident_id}}
        result = self.graph.invoke(initial_state, config=config)
        normalized = self._normalize_result(result=result, incident_id=incident_id, config=config)
        normalized["updated_at"] = current_timestamp()
        filtered_anomalies, suppressed_anomalies = self.incident_tracker.filter_anomalies(
            incident_id=incident_id,
            anomalies=list(normalized.get("anomalies", [])),
            deduplicate=deduplicate,
        )
        normalized["anomalies"] = filtered_anomalies
        normalized["suppressed_anomalies"] = suppressed_anomalies
        normalized["tracker_anomalies"] = list(filtered_anomalies)
        if deduplicate and suppressed_anomalies and not filtered_anomalies:
            normalized["status"] = "suppressed"
        with self._lock:
            self._latest_states[incident_id] = normalized
            if normalized.get("awaiting_human"):
                self._pending_incidents.add(incident_id)
            else:
                self._pending_incidents.discard(incident_id)
        self.incident_tracker.hydrate_incident(normalized)
        return normalized

    def _normalize_result(self, *, result: dict[str, Any], incident_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = dict(result)
        normalized.setdefault("incident_id", incident_id)
        if "__interrupt__" in normalized:
            snapshot = self._read_checkpoint_state(incident_id, config=config)
            if snapshot is not None:
                normalized = self._snapshot_to_incident(snapshot=snapshot, incident_id=incident_id)
            else:
                normalized["awaiting_human"] = True
                normalized["status"] = "awaiting_human"
        elif normalized.get("error"):
            normalized["status"] = "error"
        else:
            normalized["status"] = "completed"
        return normalized

    def _hydrate_from_checkpoints(self) -> None:
        for incident_id in self.checkpointer.list_threads():
            snapshot = self._read_checkpoint_state(incident_id)
            if snapshot is None:
                continue
            normalized = self._snapshot_to_incident(snapshot=snapshot, incident_id=incident_id)
            with self._lock:
                self._latest_states[incident_id] = normalized
                if normalized.get("awaiting_human"):
                    self._pending_incidents.add(incident_id)
                else:
                    self._pending_incidents.discard(incident_id)
            self.incident_tracker.hydrate_incident(normalized)

    def _read_checkpoint_state(self, incident_id: str, config: dict[str, Any] | None = None) -> Any | None:
        checkpoint_config = config or {"configurable": {"thread_id": incident_id}}
        try:
            return self.graph.get_state(checkpoint_config)
        except Exception:
            return None

    def _snapshot_to_incident(self, *, snapshot: Any, incident_id: str) -> dict[str, Any]:
        values = dict(snapshot.values or {})
        values.setdefault("incident_id", incident_id)
        values.setdefault("created_at", current_timestamp())
        values.setdefault("updated_at", current_timestamp())
        interrupts = [interrupt.value for interrupt in snapshot.interrupts]
        if not values.get("slack_message_ts"):
            values["slack_message_ts"] = _interrupt_slack_message_ts(interrupts)
        values["anomalies"] = _scoped_anomalies(values)
        values["awaiting_human"] = bool(snapshot.interrupts or snapshot.next)
        if values["awaiting_human"]:
            values["status"] = "awaiting_human"
        elif values.get("error"):
            values["status"] = "error"
        else:
            values["status"] = "completed"
        values["checkpoint"] = snapshot.config
        values["interrupts"] = interrupts
        values["tracker_anomalies"] = list(values.get("anomalies") or [])
        return values

    def prune_runtime_state(self, *, keep_incidents: int = 5) -> dict[str, int]:
        self._hydrate_from_checkpoints()
        with self._lock:
            ordered = sorted(
                self._latest_states.items(),
                key=lambda item: str(item[1].get("updated_at") or item[1].get("created_at") or ""),
                reverse=True,
            )
            keep_ids = {incident_id for incident_id, _ in ordered[:keep_incidents]}
            remove_ids = [incident_id for incident_id, _ in ordered[keep_incidents:]]
            for incident_id in remove_ids:
                self._latest_states.pop(incident_id, None)
                self._pending_incidents.discard(incident_id)
                self.checkpointer.delete_thread(incident_id)

        return {
            "remaining_incidents": len(keep_ids),
            "removed_incidents": len(remove_ids),
        }

    def reset_runtime_state(self) -> dict[str, int]:
        with self._lock:
            incident_count = len(self._latest_states)
            pending_count = len(self._pending_incidents)
            self._latest_states.clear()
            self._pending_incidents.clear()
        checkpoint_count = len(self.checkpointer.list_threads())
        self.checkpointer.reset()
        self.incident_tracker.reset()
        return {
            "cleared_incidents": incident_count,
            "cleared_pending_incidents": pending_count,
            "cleared_checkpoints": checkpoint_count,
        }


def _interrupt_slack_message_ts(interrupts: list[Any]) -> str | None:
    for interrupt in interrupts:
        if not isinstance(interrupt, dict):
            continue
        slack_response = interrupt.get("slack_response")
        if isinstance(slack_response, dict) and slack_response.get("ts"):
            return str(slack_response["ts"])
    return None


def _scoped_anomalies(values: dict[str, Any]) -> list[Any]:
    anomalies = list(values.get("anomalies") or [])
    if not anomalies:
        return anomalies

    seeded_resource_names = {str(name) for name in values.get("seeded_resource_names", []) if name}
    if not seeded_resource_names:
        plan = values.get("plan") or {}
        target_name = str(plan.get("target_name") or "")
        if target_name:
            seeded_resource_names = {target_name}
    if not seeded_resource_names:
        return anomalies

    filtered = [anomaly for anomaly in anomalies if str(anomaly.get("resource_name") or "") in seeded_resource_names]
    return filtered or anomalies
