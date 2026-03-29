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
            "events": [],
            "error": None,
        }

    def get_pod_logs(self, name: str, namespace: str, tail_lines: int = 200) -> str:
        if self.mode == "oomkill":
            return "memory limit exceeded while processing request"
        return "application crashed with exit code 1"

    def describe_pod(self, name: str, namespace: str):
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

    def delete_pod(self, name: str, namespace: str):
        self.deleted.append((namespace, name))
        return {"ok": True, "message": f"Deleted pod {namespace}/{name}."}

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

    def send_message(self, *, channel=None, text: str, blocks=None):
        payload = {"ok": True, "stub": True, "channel": channel or self.default_channel, "text": text, "blocks": blocks}
        self.messages.append(payload)
        return payload


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
        prometheus_url=None,
        audit_log_path=str(tmp_path / "audit.jsonl"),
        checkpoint_store_path=str(tmp_path / "checkpoints.pkl"),
        verify_timeout_seconds=1,
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
    assert "Increase memory limit" in result["plan"]["parameters"]["recommendation"]
    assert slack_client.messages
