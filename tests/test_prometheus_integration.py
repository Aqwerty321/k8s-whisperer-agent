from backend.app.integrations.prometheus import PrometheusClient
from backend.app.mcp import build_prometheus_mcp_server


class StubPrometheusClient(PrometheusClient):
    def __init__(self) -> None:
        super().__init__(base_url="http://prometheus.example")

    def query(self, promql: str):
        return {"status": "success", "query": promql, "data": {"result": []}}

    def get_cpu_throttling(self, *, namespace: str, lookback: str = PrometheusClient.CPU_THROTTLING_LOOKBACK):
        return {
            "status": "success",
            "error": None,
            "metrics": [
                {
                    "namespace": namespace,
                    "pod": "demo-api-123",
                    "ratio": 0.61,
                    "threshold": 0.5,
                }
            ],
        }


def test_prometheus_client_reports_unconfigured_state() -> None:
    client = PrometheusClient(base_url=None)

    result = client.get_cpu_throttling(namespace="default")

    assert result["status"] == "error"
    assert result["metrics"] == []


def test_build_prometheus_mcp_server_exposes_tools() -> None:
    server = build_prometheus_mcp_server(StubPrometheusClient())

    assert server is not None


def test_prometheus_client_verifies_cpu_throttling_recovery() -> None:
    client = StubPrometheusClient()

    result = client.verify_cpu_throttling_recovery(
        namespace="default",
        pod_names=["demo-api-123"],
        threshold=0.5,
        timeout_seconds=1,
        poll_interval_seconds=0.01,
    )

    assert result["ok"] is False
    assert result["recovered"] is False
    assert "above threshold" in result["message"]
