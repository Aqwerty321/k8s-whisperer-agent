from backend.app.integrations.prometheus import PrometheusClient
from backend.app.mcp import build_prometheus_mcp_server


class StubPrometheusClient(PrometheusClient):
    def __init__(self) -> None:
        super().__init__(base_url="http://prometheus.example")

    def query(self, promql: str):
        return {"status": "success", "query": promql, "data": {"result": []}}

    def get_cpu_throttling(self, *, namespace: str):
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
