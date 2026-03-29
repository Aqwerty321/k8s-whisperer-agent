from __future__ import annotations

import time
from urllib.parse import urlparse
from typing import Any


class K8sClient:
    def __init__(self, kubeconfig: str | None = None) -> None:
        self.kubeconfig = kubeconfig
        self._core_v1: Any | None = None
        self._load_error: str | None = None

    def _ensure_client(self) -> None:
        if self._core_v1 is not None or self._load_error is not None:
            return

        try:
            from kubernetes import client, config

            if self.kubeconfig:
                try:
                    config.load_kube_config(config_file=self.kubeconfig)
                except Exception:
                    config.load_incluster_config()
            else:
                try:
                    config.load_kube_config()
                except Exception:
                    config.load_incluster_config()

            self._core_v1 = client.CoreV1Api()
        except Exception as exc:
            self._load_error = str(exc)

    def is_available(self) -> bool:
        self._ensure_client()
        return self._core_v1 is not None

    def get_cluster_snapshot(self, namespace: str) -> dict[str, Any]:
        self._ensure_client()
        return {
            "pods": self.get_pods(namespace),
            "events": self.get_events(namespace),
            "error": self._load_error,
        }

    def get_pods(self, namespace: str) -> list[dict[str, Any]]:
        self._ensure_client()
        if self._core_v1 is None:
            return []

        try:
            pods = self._core_v1.list_namespaced_pod(namespace=namespace).items
            return [self._serialize_pod(pod) for pod in pods]
        except Exception as exc:
            self._load_error = str(exc)
            return []

    def get_events(self, namespace: str) -> list[dict[str, Any]]:
        self._ensure_client()
        if self._core_v1 is None:
            return []

        try:
            events = self._core_v1.list_namespaced_event(namespace=namespace).items
            return [self._serialize_event(event) for event in events]
        except Exception as exc:
            self._load_error = str(exc)
            return []

    def get_pod_logs(self, name: str, namespace: str, tail_lines: int = 200) -> str:
        self._ensure_client()
        if self._core_v1 is None:
            return "Kubernetes client is not configured."

        try:
            return str(
                self._core_v1.read_namespaced_pod_log(
                    name=name,
                    namespace=namespace,
                    tail_lines=tail_lines,
                )
            )
        except Exception as exc:
            return f"Unable to fetch logs: {self._format_error(exc)}"

    def describe_pod(self, name: str, namespace: str) -> dict[str, Any]:
        self._ensure_client()
        if self._core_v1 is None:
            return {
                "name": name,
                "namespace": namespace,
                "pod": None,
                "events": [],
                "error": self._load_error or "Kubernetes client is not configured.",
            }

        try:
            pod = self._core_v1.read_namespaced_pod(name=name, namespace=namespace)
            related_events = self._core_v1.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={name}",
            ).items
            return {
                "name": name,
                "namespace": namespace,
                "pod": self._serialize_pod(pod),
                "events": [self._serialize_event(event) for event in related_events],
                "error": None,
            }
        except Exception as exc:
            return {
                "name": name,
                "namespace": namespace,
                "pod": None,
                "events": [],
                "error": self._format_error(exc),
            }

    def delete_pod(self, name: str, namespace: str) -> dict[str, Any]:
        self._ensure_client()
        if self._core_v1 is None:
            return {
                "ok": False,
                "message": self._load_error or "Kubernetes client is not configured.",
            }

        try:
            self._core_v1.delete_namespaced_pod(name=name, namespace=namespace)
            return {"ok": True, "message": f"Deleted pod {namespace}/{name}."}
        except Exception as exc:
            return {"ok": False, "message": self._format_error(exc)}

    def patch_pod(self, name: str, namespace: str, patch: dict[str, Any]) -> dict[str, Any]:
        self._ensure_client()
        if self._core_v1 is None:
            return {
                "ok": False,
                "message": self._load_error or "Kubernetes client is not configured.",
            }

        try:
            response = self._core_v1.patch_namespaced_pod(
                name=name,
                namespace=namespace,
                body=patch,
            )
            return {
                "ok": True,
                "message": f"Patched pod {namespace}/{name}.",
                "resource_version": getattr(response.metadata, "resource_version", None),
            }
        except Exception as exc:
            return {"ok": False, "message": self._format_error(exc)}

    def _format_error(self, exc: Exception) -> str:
        status = getattr(exc, "status", None)
        reason = getattr(exc, "reason", None)
        if status == 404:
            return "Pod was not found. It may have already restarted or been deleted."
        if status and reason:
            return f"Kubernetes API error {status}: {reason}"

        message = str(exc).strip()
        if not message:
            return "Unknown Kubernetes API error."
        first_line = message.splitlines()[0].strip()
        parsed = urlparse(first_line)
        if parsed.scheme and parsed.netloc:
            return f"Kubernetes API request failed for {parsed.path or '/'}"
        if len(first_line) > 200:
            return first_line[:197] + "..."
        return first_line

    def verify_pod_recovery(
        self,
        *,
        name: str,
        namespace: str,
        expected_absent: bool = False,
        timeout_seconds: int = 20,
        poll_interval_seconds: float = 2.0,
    ) -> dict[str, Any]:
        self._ensure_client()
        if self._core_v1 is None:
            return {
                "ok": False,
                "recovered": False,
                "message": self._load_error or "Kubernetes client is not configured.",
                "pod": None,
            }

        deadline = time.time() + timeout_seconds
        last_snapshot: dict[str, Any] | None = None
        last_error: str | None = None

        while time.time() < deadline:
            description = self.describe_pod(name=name, namespace=namespace)
            last_snapshot = description.get("pod")
            last_error = description.get("error")

            if expected_absent:
                if last_error:
                    return {
                        "ok": True,
                        "recovered": True,
                        "message": f"Pod {namespace}/{name} is absent after deletion as expected.",
                        "pod": None,
                    }
            elif last_snapshot and self._pod_is_healthy(last_snapshot):
                return {
                    "ok": True,
                    "recovered": True,
                    "message": f"Pod {namespace}/{name} became healthy before timeout.",
                    "pod": last_snapshot,
                }

            time.sleep(poll_interval_seconds)

        return {
            "ok": False,
            "recovered": False,
            "message": last_error or f"Timed out waiting for pod {namespace}/{name} to recover.",
            "pod": last_snapshot,
        }

    def _pod_is_healthy(self, pod: dict[str, Any]) -> bool:
        if str(pod.get("phase")) != "Running":
            return False
        statuses = pod.get("container_statuses", [])
        if not statuses:
            return False
        return all(bool(status.get("ready")) for status in statuses)

    def _serialize_pod(self, pod: Any) -> dict[str, Any]:
        statuses = getattr(getattr(pod, "status", None), "container_statuses", None) or []
        owners = getattr(getattr(pod, "metadata", None), "owner_references", None) or []
        container_statuses = []
        total_restarts = 0
        waiting_reasons: list[str] = []
        owner_kind = None
        owner_name = None

        if owners:
            owner_kind, owner_name = self._normalize_owner_reference(owners[0])

        for status in statuses:
            restart_count = getattr(status, "restart_count", 0) or 0
            total_restarts += restart_count
            waiting = getattr(getattr(status, "state", None), "waiting", None)
            terminated = getattr(getattr(status, "last_state", None), "terminated", None)
            container_statuses.append(
                {
                    "name": getattr(status, "name", "unknown"),
                    "restart_count": restart_count,
                    "waiting_reason": getattr(waiting, "reason", None),
                    "terminated_reason": getattr(terminated, "reason", None),
                    "ready": getattr(status, "ready", False),
                }
            )
            if getattr(waiting, "reason", None):
                waiting_reasons.append(str(waiting.reason))

        return {
            "name": getattr(getattr(pod, "metadata", None), "name", "unknown"),
            "namespace": getattr(getattr(pod, "metadata", None), "namespace", "default"),
            "phase": getattr(getattr(pod, "status", None), "phase", "Unknown"),
            "reason": getattr(getattr(pod, "status", None), "reason", None),
            "owner_kind": owner_kind,
            "owner_name": owner_name,
            "restart_count": total_restarts,
            "waiting_reasons": waiting_reasons,
            "container_statuses": container_statuses,
        }

    def _normalize_owner_reference(self, owner: Any) -> tuple[str | None, str | None]:
        kind = getattr(owner, "kind", None)
        name = getattr(owner, "name", None)
        if kind == "ReplicaSet" and isinstance(name, str) and "-" in name:
            deployment_name = name.rsplit("-", 1)[0]
            if deployment_name:
                return "Deployment", deployment_name
        return kind, name

    def _serialize_event(self, event: Any) -> dict[str, Any]:
        involved_object = getattr(event, "involved_object", None)
        return {
            "type": getattr(event, "type", None),
            "reason": getattr(event, "reason", None),
            "message": getattr(event, "message", None),
            "namespace": getattr(getattr(event, "metadata", None), "namespace", None),
            "resource_name": getattr(involved_object, "name", None),
            "resource_kind": getattr(involved_object, "kind", None),
            "count": getattr(event, "count", None),
            "last_timestamp": str(getattr(event, "last_timestamp", "")),
        }
