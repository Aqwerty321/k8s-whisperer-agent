from __future__ import annotations

from typing import Any

from ..integrations.prometheus import PrometheusClient


def build_prometheus_mcp_server(prometheus_client: PrometheusClient):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - optional runtime import
        raise RuntimeError("The MCP SDK is not available. Install dependencies first.") from exc

    server = FastMCP("k8s-whisperer-prometheus")

    @server.tool()
    def query_prometheus(promql: str) -> dict[str, Any]:
        """Run a PromQL query against Prometheus."""
        return prometheus_client.query(promql)

    @server.tool()
    def get_cpu_throttling(namespace: str) -> dict[str, Any]:
        """Return per-pod CPU throttling ratios for a namespace."""
        return prometheus_client.get_cpu_throttling(namespace=namespace)

    return server


def main() -> None:
    from ..config import get_settings

    settings = get_settings()
    server = build_prometheus_mcp_server(PrometheusClient(base_url=settings.prometheus_url))
    server.run()


if __name__ == "__main__":
    main()
