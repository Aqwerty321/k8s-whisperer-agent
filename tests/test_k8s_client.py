from types import SimpleNamespace

from backend.app.integrations.k8s import K8sClient


def test_normalize_owner_reference_maps_replicaset_to_deployment() -> None:
    client = K8sClient()
    owner = SimpleNamespace(kind="ReplicaSet", name="demo-api-7d9b6f5d8")

    kind, name = client._normalize_owner_reference(owner)

    assert kind == "Deployment"
    assert name == "demo-api"
