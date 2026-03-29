from __future__ import annotations

from typing import Any

from ..integrations.k8s import K8sClient


def build_kubectl_mcp_server(k8s_client: K8sClient):
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - optional runtime import
        raise RuntimeError("The MCP SDK is not available. Install dependencies first.") from exc

    server = FastMCP("k8s-whisperer-kubectl")

    @server.tool()
    def list_pods(namespace: str) -> list[dict[str, Any]]:
        """List pods in a namespace."""
        return k8s_client.get_pods(namespace)

    @server.tool()
    def list_events(namespace: str) -> list[dict[str, Any]]:
        """List cluster events in a namespace."""
        return k8s_client.get_events(namespace)

    @server.tool()
    def get_pod_logs(namespace: str, pod_name: str, tail_lines: int = 200) -> str:
        """Fetch recent pod logs."""
        return k8s_client.get_pod_logs(name=pod_name, namespace=namespace, tail_lines=tail_lines)

    @server.tool()
    def describe_pod(namespace: str, pod_name: str) -> dict[str, Any]:
        """Return a describe-style pod summary."""
        return k8s_client.describe_pod(name=pod_name, namespace=namespace)

    @server.tool()
    def delete_pod(namespace: str, pod_name: str) -> dict[str, Any]:
        """Delete a pod to trigger restart by its controller."""
        return k8s_client.delete_pod(name=pod_name, namespace=namespace)

    @server.tool()
    def patch_pod(namespace: str, pod_name: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Apply a narrow patch to a pod."""
        return k8s_client.patch_pod(name=pod_name, namespace=namespace, patch=patch)

    return server


def main() -> None:
    from ..config import get_settings

    settings = get_settings()
    server = build_kubectl_mcp_server(K8sClient(kubeconfig=settings.kubeconfig))
    server.run()


if __name__ == "__main__":
    main()
