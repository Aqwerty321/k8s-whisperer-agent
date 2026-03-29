from __future__ import annotations

from threading import Lock
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from ..audit import AuditLogger
from ..config import Settings
from ..integrations.k8s import K8sClient
from ..integrations.llm import LLMClient
from ..integrations.slack import SlackClient
from ..models import WhisperState, build_initial_state
from .checkpointer import PersistentInMemorySaver
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
    builder.add_node("hitl", make_hitl_node(deps))
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
        {"execute": "execute", "hitl": "hitl"},
    )
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
        slack_client: SlackClient,
    ) -> None:
        self.deps = AgentDependencies(
            settings=settings,
            audit_logger=audit_logger,
            k8s_client=k8s_client,
            llm_client=llm_client,
            slack_client=slack_client,
        )
        self.checkpointer = PersistentInMemorySaver(settings.checkpoint_store_path)
        self.graph = build_graph(self.deps, self.checkpointer)
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
    ) -> dict[str, Any]:
        initial_state = build_initial_state(
            namespace=namespace or self.deps.settings.k8s_namespace,
            slack_channel=slack_channel or self.deps.settings.slack_default_channel,
            seed_events=seed_events,
        )
        return self._invoke_with_config(initial_state=initial_state)

    def resume_incident(self, *, incident_id: str, approved: bool) -> dict[str, Any]:
        config = {"configurable": {"thread_id": incident_id}}
        result = self.graph.invoke(Command(resume={"approved": approved}), config=config)
        normalized = self._normalize_result(result=result, incident_id=incident_id)
        with self._lock:
            self._latest_states[incident_id] = normalized
            self._pending_incidents.discard(incident_id)
        return normalized

    def get_status(self) -> dict[str, Any]:
        self._hydrate_from_checkpoints()
        with self._lock:
            return {
                "pending_incidents": sorted(self._pending_incidents),
                "latest_incidents": list(self._latest_states.values())[-10:],
                "checkpoint_threads": self.checkpointer.list_threads(),
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
        with self._lock:
            return self._latest_states.get(incident_id)

    def _invoke_with_config(self, *, initial_state: WhisperState) -> dict[str, Any]:
        incident_id = initial_state["incident_id"]
        config = {"configurable": {"thread_id": incident_id}}
        result = self.graph.invoke(initial_state, config=config)
        normalized = self._normalize_result(result=result, incident_id=incident_id, config=config)
        with self._lock:
            self._latest_states[incident_id] = normalized
            if normalized.get("awaiting_human"):
                self._pending_incidents.add(incident_id)
            else:
                self._pending_incidents.discard(incident_id)
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

    def _read_checkpoint_state(self, incident_id: str, config: dict[str, Any] | None = None) -> Any | None:
        checkpoint_config = config or {"configurable": {"thread_id": incident_id}}
        try:
            return self.graph.get_state(checkpoint_config)
        except Exception:
            return None

    def _snapshot_to_incident(self, *, snapshot: Any, incident_id: str) -> dict[str, Any]:
        values = dict(snapshot.values or {})
        values.setdefault("incident_id", incident_id)
        values["awaiting_human"] = bool(snapshot.interrupts or snapshot.next)
        if values["awaiting_human"]:
            values["status"] = "awaiting_human"
        elif values.get("error"):
            values["status"] = "error"
        else:
            values["status"] = "completed"
        values["checkpoint"] = snapshot.config
        values["interrupts"] = [interrupt.value for interrupt in snapshot.interrupts]
        return values
