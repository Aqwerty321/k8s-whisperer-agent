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
