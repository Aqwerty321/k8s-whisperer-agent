from types import SimpleNamespace

from backend.app.integrations.k8s import K8sClient


class FakeApiError(Exception):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(f"({status})\nReason: {reason}")
        self.status = status
        self.reason = reason


def test_normalize_owner_reference_maps_replicaset_to_deployment() -> None:
    client = K8sClient()
    owner = SimpleNamespace(kind="ReplicaSet", name="demo-api-7d9b6f5d8")

    kind, name = client._normalize_owner_reference(owner)

    assert kind == "Deployment"
    assert name == "demo-api"


def test_format_error_simplifies_not_found_api_errors() -> None:
    client = K8sClient()

    message = client._format_error(FakeApiError(status=404, reason="Not Found"))

    assert message == "Pod was not found. It may have already restarted or been deleted."


def test_format_error_includes_status_reason_for_non_404_api_errors() -> None:
    client = K8sClient()

    message = client._format_error(FakeApiError(status=403, reason="Forbidden"))

    assert message == "Kubernetes API error 403: Forbidden"


def test_serialize_node_extracts_ready_condition_details() -> None:
    client = K8sClient()
    node = SimpleNamespace(
        metadata=SimpleNamespace(name="minikube", creation_timestamp=None),
        spec=SimpleNamespace(unschedulable=True),
        status=SimpleNamespace(
            conditions=[
                SimpleNamespace(
                    type="Ready",
                    status="False",
                    reason="KubeletNotReady",
                    message="container runtime is down",
                )
            ]
        ),
    )

    serialized = client._serialize_node(node)

    assert serialized["name"] == "minikube"
    assert serialized["ready_status"] == "False"
    assert serialized["ready_reason"] == "KubeletNotReady"
    assert serialized["ready_message"] == "container runtime is down"
    assert serialized["unschedulable"] is True
    assert serialized["conditions"][0]["type"] == "Ready"


def test_serialize_pod_prefers_current_terminated_state_reason() -> None:
    client = K8sClient()
    pod = SimpleNamespace(
        metadata=SimpleNamespace(name="demo", namespace="default", creation_timestamp=None, owner_references=[]),
        status=SimpleNamespace(
            phase="Running",
            reason=None,
            container_statuses=[
                SimpleNamespace(
                    name="demo",
                    restart_count=1,
                    ready=False,
                    state=SimpleNamespace(
                        waiting=None,
                        terminated=SimpleNamespace(reason="OOMKilled"),
                    ),
                    last_state=SimpleNamespace(terminated=None),
                )
            ],
        ),
    )

    serialized = client._serialize_pod(pod)

    assert serialized["container_statuses"][0]["terminated_reason"] == "OOMKilled"
