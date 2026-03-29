from pathlib import Path

from backend.app.agent.graph import AgentRuntime
from backend.app.audit import AuditLogger
from backend.app.config import Settings
from backend.app.integrations.k8s import K8sClient
from backend.app.integrations.llm import LLMClient
from backend.app.integrations.slack import SlackClient


class FakeK8sClient(K8sClient):
    def __init__(self) -> None:
        super().__init__(kubeconfig=None)
        self.deleted: list[tuple[str, str]] = []
        self.patched_workloads: list[tuple[str, str, str, dict]] = []
        self.mode = "crashloop"

    def get_cluster_snapshot(self, namespace: str):
        if self.mode == "oomkill":
            return {
                "pods": [
                    {
                        "name": "demo-oomkill",
                        "namespace": namespace,
                        "phase": "Running",
                        "reason": None,
                        "restart_count": 1,
                        "waiting_reasons": [],
                        "container_statuses": [
                            {
                                "name": "memory-hog",
                                "restart_count": 1,
                                "waiting_reason": None,
                                "terminated_reason": "OOMKilled",
                                "ready": False,
                            }
                        ],
                    }
                ],
                "events": [],
                "error": None,
            }

        if self.mode == "pending":
            return {
                "pods": [
                    {
                        "name": "demo-pending",
                        "namespace": namespace,
                        "phase": "Pending",
                        "reason": "Unschedulable",
                        "age_seconds": 600,
                        "restart_count": 0,
                        "waiting_reasons": [],
                        "container_statuses": [],
                    }
                ],
                "nodes": [],
                "events": [
                    {
                        "type": "Warning",
                        "reason": "FailedScheduling",
                        "message": "0/1 nodes are available: 1 Insufficient memory.",
                        "namespace": namespace,
                        "resource_name": "demo-pending",
                        "resource_kind": "Pod",
                        "count": 3,
                        "last_timestamp": "2026-03-29T00:00:00Z",
                    }
                ],
                "error": None,
            }

        if self.mode == "node_not_ready":
            return {
                "pods": [],
                "nodes": [
                    {
                        "name": "minikube",
                        "ready_status": "False",
                        "ready_reason": "KubeletNotReady",
                        "ready_message": "container runtime is down",
                        "unschedulable": True,
                    }
                ],
                "events": [],
                "error": None,
            }

        return {
            "pods": [
                {
                    "name": "demo-crashloop",
                    "namespace": namespace,
                    "phase": "Running",
                    "reason": None,
                    "restart_count": 6,
                    "waiting_reasons": ["CrashLoopBackOff"],
                    "container_statuses": [
                        {
                            "name": "demo",
                            "restart_count": 6,
                            "waiting_reason": "CrashLoopBackOff",
                            "terminated_reason": None,
                            "ready": False,
                        }
                    ],
                }
            ],
            "nodes": [],
            "events": [],
            "error": None,
        }

    def get_pod_logs(self, name: str, namespace: str, tail_lines: int = 200) -> str:
        if self.mode == "pending":
            return ""
        if self.mode == "oomkill":
            return "memory limit exceeded while processing request"
        return "application crashed with exit code 1"

    def describe_pod(self, name: str, namespace: str):
        if self.mode == "pending":
            return {
                "name": name,
                "namespace": namespace,
                "pod": {
                    "name": name,
                    "namespace": namespace,
                    "phase": "Pending",
                    "reason": "Unschedulable",
                    "age_seconds": 600,
                    "restart_count": 0,
                    "waiting_reasons": [],
                    "container_statuses": [],
                },
                "events": [
                    {
                        "type": "Warning",
                        "reason": "FailedScheduling",
                        "message": "0/1 nodes are available: 1 Insufficient memory.",
                    }
                ],
                "error": None,
            }

        if self.mode == "oomkill":
            return {
                "name": name,
                "namespace": namespace,
                "pod": {
                    "name": name,
                    "namespace": namespace,
                    "phase": "Running",
                    "reason": None,
                    "restart_count": 1,
                    "waiting_reasons": [],
                    "container_statuses": [{"name": "memory-hog", "ready": False, "terminated_reason": "OOMKilled"}],
                },
                "events": [],
                "error": None,
            }

        return {
            "name": name,
            "namespace": namespace,
            "pod": {
                "name": name,
                "namespace": namespace,
                "phase": "Running",
                "reason": None,
                "restart_count": 6,
                "waiting_reasons": ["CrashLoopBackOff"],
                "container_statuses": [{"name": "demo", "ready": False}],
            },
            "events": [],
            "error": None,
        }

    def describe_node(self, name: str):
        return {
            "name": name,
            "node": {
                "name": name,
                "ready_status": "False",
                "ready_reason": "KubeletNotReady",
                "ready_message": "container runtime is down",
                "unschedulable": True,
            },
            "events": [],
            "error": None,
        }

    def delete_pod(self, name: str, namespace: str):
        self.deleted.append((namespace, name))
        return {"ok": True, "message": f"Deleted pod {namespace}/{name}."}

    def patch_workload(self, *, kind: str, name: str, namespace: str, patch: dict):
        self.patched_workloads.append((kind, namespace, name, patch))
        return {"ok": True, "message": f"Patched {kind} {namespace}/{name}."}

    def verify_workload_rollout(self, *, kind: str, name: str, namespace: str, timeout_seconds: int = 60, poll_interval_seconds: float = 2.0):
        return {
            "ok": True,
            "recovered": True,
            "message": f"{kind} {namespace}/{name} rollout completed successfully.",
            "resource": {
                "replicas": 1,
                "available_replicas": 1,
                "ready_replicas": 1,
            },
        }

    def verify_pod_recovery(self, **kwargs):
        return {
            "ok": True,
            "recovered": True,
            "message": "Pod recovered and is healthy.",
            "pod": {
                "name": kwargs["name"],
                "namespace": kwargs["namespace"],
                "phase": "Running",
                "container_statuses": [{"ready": True}],
            },
        }


class RecordingSlackClient(SlackClient):
    def __init__(self) -> None:
        super().__init__(
            bot_token="",
            signing_secret="",
            default_channel="#alerts",
            public_base_url="http://localhost:8000",
        )
        self.messages: list[dict] = []
        self.updates: list[dict] = []

    def send_message(self, *, channel=None, text: str, blocks=None):
        payload = {
            "ok": True,
            "stub": True,
            "channel": channel or self.default_channel,
            "text": text,
            "blocks": blocks,
            "ts": f"stub-{len(self.messages) + 1}",
        }
        self.messages.append(payload)
        return payload

    def update_message(self, *, channel=None, ts=None, text: str, blocks=None):
        payload = {
            "ok": True,
            "stub": True,
            "channel": channel or self.default_channel,
            "ts": ts,
            "text": text,
            "blocks": blocks,
        }
        self.updates.append(payload)
        return payload


class NotFoundAfterRestartK8sClient(FakeK8sClient):
    def verify_pod_recovery(self, **kwargs):
        return {
            "ok": False,
            "recovered": False,
            "message": "Pod was not found. It may have already restarted or been deleted.",
            "pod": None,
        }


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        port=8000,
        slack_bot_token="",
        slack_signing_secret="",
        slack_default_channel="#alerts",
        public_base_url="http://localhost:8000",
        gemini_api_key="",
        kubeconfig=None,
        k8s_namespace="default",
        poll_interval_seconds=30,
        auto_approve_threshold=0.8,
        incident_dedup_window_seconds=300,
        prometheus_url=None,
        audit_log_path=str(tmp_path / "audit.jsonl"),
        checkpoint_store_path=str(tmp_path / "checkpoints.pkl"),
        verify_timeout_seconds=1,
        allow_workload_patches=False,
    )


def test_runtime_completes_crashloop_with_auto_restart(tmp_path) -> None:
    settings = build_settings(tmp_path)
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=FakeK8sClient(),
        llm_client=LLMClient(api_key=""),
        slack_client=RecordingSlackClient(),
    )

    result = runtime.run_once(namespace="default")

    assert result["status"] == "completed"
    assert result["plan"]["action"] == "restart_pod"
    assert "Pod recovered and is healthy" in result["result"]
    assert result["approved"] is True


def test_runtime_recovers_pending_incident_from_persistent_checkpoint(tmp_path) -> None:
    settings = build_settings(tmp_path)
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=FakeK8sClient(),
        llm_client=LLMClient(api_key=""),
        slack_client=RecordingSlackClient(),
    )

    incident_id = "incident-hitl-1"
    config = {"configurable": {"thread_id": incident_id}}
    runtime.graph.update_state(
        config,
        {
            "incident_id": incident_id,
            "namespace": "default",
            "awaiting_human": True,
            "plan": {
                "action": "escalate_to_human",
                "target_kind": "Pod",
                "target_name": "demo-crashloop",
                "namespace": "default",
                "parameters": {},
                "confidence": 0.4,
                "blast_radius": "high",
                "reason": "Needs approval",
                "requires_human": True,
            },
        },
        as_node="hitl",
    )

    rehydrated = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=FakeK8sClient(),
        llm_client=LLMClient(api_key=""),
        slack_client=RecordingSlackClient(),
    )

    incident = rehydrated.get_incident(incident_id)
    assert incident is not None
    assert incident["incident_id"] == incident_id


def test_runtime_routes_oomkill_to_hitl_recommendation(tmp_path) -> None:
    settings = build_settings(tmp_path)
    k8s_client = FakeK8sClient()
    k8s_client.mode = "oomkill"
    slack_client = RecordingSlackClient()
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=k8s_client,
        llm_client=LLMClient(api_key=""),
        slack_client=slack_client,
    )

    result = runtime.run_once(namespace="default")

    assert result["status"] == "awaiting_human"
    assert result["plan"]["action"] == "patch_pod"
    assert result["plan"]["requires_human"] is True
    assert "memory limit" in result["plan"]["parameters"]["recommendation"]
    assert len(result["anomalies"]) == 1
    assert result["anomalies"][0]["anomaly_type"] == "OOMKilled"
    assert result["anomalies"][0]["resource_name"] == "demo-oomkill"
    assert len(slack_client.messages) == 1
    assert result["slack_message_ts"] == "stub-1"

    resumed = runtime.resume_incident(incident_id=result["incident_id"], approved=True)

    assert resumed["status"] == "completed"
    assert len(slack_client.messages) == 1


def test_runtime_marks_rejected_hitl_incident_with_explicit_result(tmp_path) -> None:
    settings = build_settings(tmp_path)
    k8s_client = FakeK8sClient()
    k8s_client.mode = "oomkill"
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=k8s_client,
        llm_client=LLMClient(api_key=""),
        slack_client=RecordingSlackClient(),
    )

    pending = runtime.run_once(namespace="default")
    rejected = runtime.resume_incident(incident_id=pending["incident_id"], approved=False)

    assert rejected["status"] == "completed"
    assert rejected["approved"] is False
    assert rejected["result"] == "Operator rejected remediation. No cluster mutation was executed."


def test_runtime_pending_pod_recommendation_uses_scheduling_evidence(tmp_path) -> None:
    settings = build_settings(tmp_path)
    k8s_client = FakeK8sClient()
    k8s_client.mode = "pending"
    slack_client = RecordingSlackClient()
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=k8s_client,
        llm_client=LLMClient(api_key=""),
        slack_client=slack_client,
    )

    result = runtime.run_once(namespace="default")

    assert result["status"] == "awaiting_human"
    assert result["plan"]["action"] == "notify_only"
    assert len(result["anomalies"]) == 1
    assert result["anomalies"][0]["resource_name"] == "demo-pending"
    assert "memory" in result["plan"]["parameters"]["recommendation"].lower()
    assert any("Insufficient memory" in item for item in result["anomalies"][0]["evidence"])


def test_runtime_does_not_flag_fresh_pending_pod_before_threshold(tmp_path) -> None:
    settings = build_settings(tmp_path)
    k8s_client = FakeK8sClient()
    k8s_client.mode = "pending"
    k8s_client.get_cluster_snapshot = lambda namespace: {
        "pods": [
            {
                "name": "demo-pending",
                "namespace": namespace,
                "phase": "Pending",
                "reason": "Unschedulable",
                "age_seconds": 120,
                "restart_count": 0,
                "waiting_reasons": [],
                "container_statuses": [],
            }
        ],
        "nodes": [],
        "events": [],
        "error": None,
    }
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=k8s_client,
        llm_client=LLMClient(api_key=""),
        slack_client=RecordingSlackClient(),
    )

    result = runtime.run_once(namespace="default")

    assert result["status"] == "completed"
    assert result["anomalies"] == []


def test_runtime_focuses_seeded_walkthrough_on_matching_resource(tmp_path) -> None:
    settings = build_settings(tmp_path)
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=FakeK8sClient(),
        llm_client=LLMClient(api_key=""),
        slack_client=RecordingSlackClient(),
    )

    result = runtime.run_once(
        namespace="default",
        seed_events=[
            {
                "type": "Warning",
                "reason": "OOMKilled",
                "message": "Container was OOMKilled after hitting memory limit",
                "namespace": "default",
                "resource_name": "demo-oomkill",
                "resource_kind": "Pod",
            }
        ],
    )

    assert [anomaly["resource_name"] for anomaly in result["anomalies"]] == ["demo-oomkill"]


def test_runtime_checkpoint_view_scopes_anomalies_to_plan_target(tmp_path) -> None:
    settings = build_settings(tmp_path)
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=FakeK8sClient(),
        llm_client=LLMClient(api_key=""),
        slack_client=RecordingSlackClient(),
    )

    incident_id = "incident-checkpoint-scope-1"
    config = {"configurable": {"thread_id": incident_id}}
    runtime.graph.update_state(
        config,
        {
            "incident_id": incident_id,
            "namespace": "default",
            "anomalies": [
                {"anomaly_type": "OOMKilled", "resource_name": "demo-oomkill"},
                {"anomaly_type": "CrashLoopBackOff", "resource_name": "demo-crashloop"},
            ],
            "plan": {
                "action": "patch_pod",
                "target_name": "demo-oomkill",
                "namespace": "default",
                "requires_human": True,
            },
        },
        as_node="plan",
    )

    incident = runtime.get_incident(incident_id)

    assert incident is not None
    assert [anomaly["resource_name"] for anomaly in incident["anomalies"]] == ["demo-oomkill"]


def test_runtime_treats_missing_old_pod_after_restart_as_completed(tmp_path) -> None:
    settings = build_settings(tmp_path)
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=NotFoundAfterRestartK8sClient(),
        llm_client=LLMClient(api_key=""),
        slack_client=RecordingSlackClient(),
    )

    result = runtime.run_once(namespace="default")

    assert result["status"] == "completed"
    assert result["approved"] is True
    assert "Restart request accepted" in result["result"]


def test_runtime_deduplicates_repeat_incidents_for_poller_mode(tmp_path) -> None:
    settings = build_settings(tmp_path)
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=FakeK8sClient(),
        llm_client=LLMClient(api_key=""),
        slack_client=RecordingSlackClient(),
    )

    first = runtime.run_once(namespace="default", deduplicate=True)
    second = runtime.run_once(namespace="default", deduplicate=True)

    assert first["status"] == "completed"
    assert second["status"] == "suppressed"
    assert second["anomalies"] == []
    assert len(second["suppressed_anomalies"]) == 1


def test_runtime_maps_owner_hints_from_pod_metadata(tmp_path) -> None:
    settings = build_settings(tmp_path)
    k8s_client = FakeK8sClient()
    k8s_client.mode = "oomkill"
    k8s_client.get_cluster_snapshot = lambda namespace: {
        "pods": [
            {
                "name": "demo-oomkill",
                "namespace": namespace,
                "phase": "Running",
                "reason": None,
                "owner_kind": "Deployment",
                "owner_name": "demo-api",
                "restart_count": 1,
                "waiting_reasons": [],
                "container_statuses": [
                    {
                        "name": "memory-hog",
                        "restart_count": 1,
                        "waiting_reason": None,
                        "terminated_reason": "OOMKilled",
                        "ready": False,
                    }
                ],
            }
        ],
        "nodes": [],
        "events": [],
        "error": None,
    }
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=k8s_client,
        llm_client=LLMClient(api_key=""),
        slack_client=RecordingSlackClient(),
    )

    result = runtime.run_once(namespace="default")

    assert result["anomalies"][0]["workload_kind"] == "Deployment"
    assert result["anomalies"][0]["workload_name"] == "demo-api"
    assert "Deployment `demo-api`" in result["plan"]["parameters"]["recommendation"]


def test_runtime_executes_real_workload_patch_for_deployment_owned_oomkill(tmp_path) -> None:
    settings = build_settings(tmp_path)
    settings = settings.model_copy(update={"allow_workload_patches": True})
    k8s_client = FakeK8sClient()
    k8s_client.mode = "oomkill"
    k8s_client.get_cluster_snapshot = lambda namespace: {
        "pods": [
            {
                "name": "demo-oomkill-abc123",
                "namespace": namespace,
                "phase": "Running",
                "reason": None,
                "owner_kind": "Deployment",
                "owner_name": "demo-oomkill",
                "restart_count": 1,
                "waiting_reasons": [],
                "container_statuses": [
                    {
                        "name": "memory-hog",
                        "restart_count": 1,
                        "waiting_reason": None,
                        "terminated_reason": "OOMKilled",
                        "ready": False,
                    }
                ],
            }
        ],
        "nodes": [],
        "events": [],
        "error": None,
    }
    slack_client = RecordingSlackClient()
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=k8s_client,
        llm_client=LLMClient(api_key="", allow_workload_patches=True),
        slack_client=slack_client,
    )

    pending = runtime.run_once(namespace="default")
    completed = runtime.resume_incident(incident_id=pending["incident_id"], approved=True)

    assert completed["status"] == "completed"
    assert k8s_client.patched_workloads
    kind, namespace, name, patch = k8s_client.patched_workloads[0]
    assert kind == "Deployment"
    assert namespace == "default"
    assert name == "demo-oomkill"
    assert patch["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"] == "96Mi"
    assert "rollout completed successfully" in completed["result"]


def test_runtime_prefers_owned_workload_anomaly_for_seeded_oomkill(tmp_path) -> None:
    settings = build_settings(tmp_path)
    settings = settings.model_copy(update={"allow_workload_patches": True})
    k8s_client = FakeK8sClient()
    k8s_client.mode = "oomkill"
    k8s_client.get_cluster_snapshot = lambda namespace: {
        "pods": [
            {
                "name": "demo-oomkill-abc123",
                "namespace": namespace,
                "phase": "Running",
                "reason": None,
                "owner_kind": "Deployment",
                "owner_name": "demo-oomkill",
                "restart_count": 1,
                "waiting_reasons": [],
                "container_statuses": [
                    {
                        "name": "memory-hog",
                        "restart_count": 1,
                        "waiting_reason": None,
                        "terminated_reason": "OOMKilled",
                        "ready": False,
                    }
                ],
            }
        ],
        "nodes": [],
        "events": [],
        "error": None,
    }
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=k8s_client,
        llm_client=LLMClient(api_key="", allow_workload_patches=True),
        slack_client=RecordingSlackClient(),
    )

    result = runtime.run_once(
        namespace="default",
        seed_events=[
            {
                "type": "Warning",
                "reason": "OOMKilled",
                "message": "Container was OOMKilled after hitting memory limit",
                "namespace": "default",
                "resource_name": "demo-oomkill",
                "resource_kind": "Pod",
            }
        ],
    )

    assert result["anomalies"][0]["workload_kind"] == "Deployment"
    assert result["anomalies"][0]["workload_name"] == "demo-oomkill"
    assert result["plan"]["parameters"]["patch"] is not None


def test_runtime_default_profile_keeps_deployment_owned_oomkill_as_recommendation_only(tmp_path) -> None:
    settings = build_settings(tmp_path)
    k8s_client = FakeK8sClient()
    k8s_client.mode = "oomkill"
    k8s_client.get_cluster_snapshot = lambda namespace: {
        "pods": [
            {
                "name": "demo-oomkill-abc123",
                "namespace": namespace,
                "phase": "Running",
                "reason": None,
                "owner_kind": "Deployment",
                "owner_name": "demo-oomkill",
                "restart_count": 1,
                "waiting_reasons": [],
                "container_statuses": [
                    {
                        "name": "memory-hog",
                        "restart_count": 1,
                        "waiting_reason": None,
                        "terminated_reason": "OOMKilled",
                        "ready": False,
                    }
                ],
            }
        ],
        "nodes": [],
        "events": [],
        "error": None,
    }
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=k8s_client,
        llm_client=LLMClient(api_key="", allow_workload_patches=False),
        slack_client=RecordingSlackClient(),
    )

    pending = runtime.run_once(namespace="default")
    completed = runtime.resume_incident(incident_id=pending["incident_id"], approved=True)

    assert pending["plan"]["parameters"]["patch"] is None
    assert completed["status"] == "completed"
    assert not k8s_client.patched_workloads
    assert "Patch action requires human implementation" in completed["result"]


def test_runtime_records_structured_diagnosis_evidence(tmp_path) -> None:
    settings = build_settings(tmp_path)
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=FakeK8sClient(),
        llm_client=LLMClient(api_key=""),
        slack_client=RecordingSlackClient(),
    )

    result = runtime.run_once(namespace="default")

    assert result["diagnosis_evidence"]
    assert any(item.startswith("logs:") or item.startswith("event ") for item in result["diagnosis_evidence"])


def test_runtime_escalates_node_not_ready_without_cluster_mutation(tmp_path) -> None:
    settings = build_settings(tmp_path)
    k8s_client = FakeK8sClient()
    k8s_client.mode = "node_not_ready"
    slack_client = RecordingSlackClient()
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=AuditLogger(settings.audit_log_path),
        k8s_client=k8s_client,
        llm_client=LLMClient(api_key=""),
        slack_client=slack_client,
    )

    result = runtime.run_once(namespace="default")

    assert result["status"] == "awaiting_human"
    assert result["plan"]["action"] == "escalate_to_human"
    assert result["anomalies"][0]["anomaly_type"] == "NodeNotReady"
    assert result["anomalies"][0]["resource_kind"] == "Node"
    assert result["anomalies"][0]["resource_name"] == "minikube"
    assert any("Ready condition is False" in item for item in result["anomalies"][0]["evidence"])
    assert any("node Ready=False" in item for item in result["diagnosis_evidence"])
    assert not k8s_client.deleted
    assert not k8s_client.patched_workloads
    assert len(slack_client.messages) == 1
