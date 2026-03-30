from __future__ import annotations

from datetime import datetime, timezone
import time
from urllib.parse import urlparse
from typing import Any


class K8sClient:
    def __init__(self, kubeconfig: str | None = None) -> None:
        self.kubeconfig = kubeconfig
        self._core_v1: Any | None = None
        self._apps_v1: Any | None = None
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
            self._apps_v1 = client.AppsV1Api()
        except Exception as exc:
            self._load_error = str(exc)

    def is_available(self) -> bool:
        self._ensure_client()
        return self._core_v1 is not None

    def get_cluster_snapshot(self, namespace: str) -> dict[str, Any]:
        self._ensure_client()
        return {
            "pods": self.get_pods(namespace),
            "deployments": self.get_deployments(namespace),
            "events": self.get_events(namespace),
            "error": self._load_error,
        }

    def get_cluster_snapshot_multi(self, namespaces: list[str] | None = None) -> dict[str, Any]:
        self._ensure_client()
        if namespaces:
            unique_namespaces = [str(namespace).strip() for namespace in namespaces if str(namespace).strip()]
            pods: list[dict[str, Any]] = []
            deployments: list[dict[str, Any]] = []
            events: list[dict[str, Any]] = []
            for namespace in unique_namespaces:
                pods.extend(self.get_pods(namespace))
                deployments.extend(self.get_deployments(namespace))
                events.extend(self.get_events(namespace))
            return {
                "pods": pods,
                "deployments": deployments,
                "events": events,
                "error": self._load_error,
                "namespaces": unique_namespaces,
            }
        return {
            "pods": self.get_pods_all_namespaces(),
            "deployments": self.get_deployments_all_namespaces(),
            "events": self.get_events_all_namespaces(),
            "error": self._load_error,
            "namespaces": ["*"],
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

    def get_pods_all_namespaces(self) -> list[dict[str, Any]]:
        self._ensure_client()
        if self._core_v1 is None:
            return []

        try:
            pods = self._core_v1.list_pod_for_all_namespaces().items
            return [self._serialize_pod(pod) for pod in pods]
        except Exception as exc:
            self._load_error = str(exc)
            return []

    def get_workload_pods(self, *, kind: str, name: str, namespace: str) -> list[dict[str, Any]]:
        pods = self.get_pods(namespace)
        normalized_kind = str(kind or "").lower()
        if normalized_kind == "deployment":
            return [
                pod
                for pod in pods
                if str(pod.get("owner_kind") or "").lower() == "deployment"
                and str(pod.get("owner_name") or "") == name
            ]
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

    def get_events_all_namespaces(self) -> list[dict[str, Any]]:
        self._ensure_client()
        if self._core_v1 is None:
            return []

        try:
            events = self._core_v1.list_event_for_all_namespaces().items
            return [self._serialize_event(event) for event in events]
        except Exception as exc:
            self._load_error = str(exc)
            return []

    def get_nodes(self) -> list[dict[str, Any]]:
        self._ensure_client()
        if self._core_v1 is None:
            return []

        try:
            nodes = self._core_v1.list_node().items
            return [self._serialize_node(node) for node in nodes]
        except Exception as exc:
            self._load_error = str(exc)
            return []

    def get_deployments(self, namespace: str) -> list[dict[str, Any]]:
        self._ensure_client()
        if self._apps_v1 is None:
            return []

        try:
            deployments = self._apps_v1.list_namespaced_deployment(namespace=namespace).items
            return [self._serialize_deployment(deployment) for deployment in deployments]
        except Exception as exc:
            self._load_error = str(exc)
            return []

    def get_deployments_all_namespaces(self) -> list[dict[str, Any]]:
        self._ensure_client()
        if self._apps_v1 is None:
            return []

        try:
            deployments = self._apps_v1.list_deployment_for_all_namespaces().items
            return [self._serialize_deployment(deployment) for deployment in deployments]
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

    def describe_node(self, name: str) -> dict[str, Any]:
        self._ensure_client()
        if self._core_v1 is None:
            return {
                "name": name,
                "node": None,
                "events": [],
                "error": self._load_error or "Kubernetes client is not configured.",
            }

        try:
            node = self._core_v1.read_node(name=name)
            return {
                "name": name,
                "node": self._serialize_node(node),
                "events": [],
                "error": None,
            }
        except Exception as exc:
            return {
                "name": name,
                "node": None,
                "events": [],
                "error": self._format_error(exc),
            }

    def describe_deployment(self, name: str, namespace: str) -> dict[str, Any]:
        self._ensure_client()
        if self._apps_v1 is None or self._core_v1 is None:
            return {
                "name": name,
                "namespace": namespace,
                "deployment": None,
                "events": [],
                "error": self._load_error or "Kubernetes client is not configured.",
            }

        try:
            deployment = self._apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
            related_events = self._core_v1.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={name},involvedObject.kind=Deployment",
            ).items
            return {
                "name": name,
                "namespace": namespace,
                "deployment": self._serialize_deployment(deployment),
                "events": [self._serialize_event(event) for event in related_events],
                "error": None,
            }
        except Exception as exc:
            return {
                "name": name,
                "namespace": namespace,
                "deployment": None,
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

    def patch_workload(self, *, kind: str, name: str, namespace: str, patch: dict[str, Any]) -> dict[str, Any]:
        self._ensure_client()
        if self._apps_v1 is None:
            return {
                "ok": False,
                "message": self._load_error or "Kubernetes client is not configured.",
            }

        try:
            normalized_kind = kind.lower()
            if normalized_kind == "deployment":
                response = self._apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=patch)
            else:
                return {"ok": False, "message": f"Unsupported workload kind for patch: {kind}"}
            return {
                "ok": True,
                "message": f"Patched {kind} {namespace}/{name}.",
                "resource_version": getattr(response.metadata, "resource_version", None),
            }
        except Exception as exc:
            return {"ok": False, "message": self._format_error(exc)}

    def verify_workload_rollout(
        self,
        *,
        kind: str,
        name: str,
        namespace: str,
        timeout_seconds: int = 60,
        poll_interval_seconds: float = 2.0,
    ) -> dict[str, Any]:
        self._ensure_client()
        if self._apps_v1 is None:
            return {
                "ok": False,
                "recovered": False,
                "message": self._load_error or "Kubernetes client is not configured.",
                "resource": None,
            }

        deadline = time.time() + timeout_seconds
        last_error: str | None = None
        last_status: dict[str, Any] | None = None
        attempt = 0

        while time.time() < deadline:
            try:
                normalized_kind = kind.lower()
                if normalized_kind != "deployment":
                    return {
                        "ok": False,
                        "recovered": False,
                        "message": f"Unsupported workload kind for rollout verification: {kind}",
                        "resource": None,
                    }

                deployment = self._apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
                spec = getattr(deployment, "spec", None)
                status = getattr(deployment, "status", None)
                replicas = int(getattr(spec, "replicas", 1) or 1)
                generation = int(getattr(getattr(deployment, "metadata", None), "generation", 0) or 0)
                observed_generation = int(getattr(status, "observed_generation", 0) or 0)
                updated_replicas = int(getattr(status, "updated_replicas", 0) or 0)
                available_replicas = int(getattr(status, "available_replicas", 0) or 0)
                ready_replicas = int(getattr(status, "ready_replicas", 0) or 0)
                last_status = {
                    "replicas": replicas,
                    "generation": generation,
                    "observed_generation": observed_generation,
                    "updated_replicas": updated_replicas,
                    "available_replicas": available_replicas,
                    "ready_replicas": ready_replicas,
                }
                if (
                    observed_generation >= generation
                    and updated_replicas >= replicas
                    and available_replicas >= replicas
                    and ready_replicas >= replicas
                ):
                    return {
                        "ok": True,
                        "recovered": True,
                        "message": f"{kind} {namespace}/{name} rollout completed successfully.",
                        "resource": last_status,
                    }
            except Exception as exc:
                last_error = self._format_error(exc)

            attempt += 1
            time.sleep(self._next_poll_delay(attempt=attempt, base_delay=poll_interval_seconds, max_delay=5.0))

        return {
            "ok": False,
            "recovered": False,
            "message": last_error or self._rollout_timeout_message(kind=kind, name=name, namespace=namespace, status=last_status),
            "resource": last_status,
        }

    def get_workload_memory_limit(self, *, kind: str, name: str, namespace: str) -> str | None:
        self._ensure_client()
        if self._apps_v1 is None:
            return None

        try:
            normalized_kind = kind.lower()
            if normalized_kind != "deployment":
                return None
            deployment = self._apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
            containers = getattr(getattr(getattr(deployment, "spec", None), "template", None), "spec", None)
            container_list = getattr(containers, "containers", None) or []
            if not container_list:
                return None
            resources = getattr(container_list[0], "resources", None)
            limits = getattr(resources, "limits", None) or {}
            return limits.get("memory")
        except Exception:
            return None

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
        workload_kind: str | None = None,
        workload_name: str | None = None,
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
        attempt = 0

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
            elif not expected_absent and workload_kind and workload_name:
                replacement = self._healthy_workload_replacement(
                    kind=workload_kind,
                    name=workload_name,
                    namespace=namespace,
                    previous_pod_name=name,
                )
                if replacement is not None:
                    return {
                        "ok": True,
                        "recovered": True,
                        "message": (
                            f"Workload {workload_kind} {namespace}/{workload_name} replaced pod {name} "
                            f"with healthy pod {replacement.get('name')}."
                        ),
                        "pod": replacement,
                    }

            attempt += 1
            time.sleep(self._next_poll_delay(attempt=attempt, base_delay=poll_interval_seconds, max_delay=5.0))

        return {
            "ok": False,
            "recovered": False,
            "message": last_error or self._pod_timeout_message(name=name, namespace=namespace, pod=last_snapshot, expected_absent=expected_absent),
            "pod": last_snapshot,
        }

    def _healthy_workload_replacement(
        self,
        *,
        kind: str,
        name: str,
        namespace: str,
        previous_pod_name: str,
    ) -> dict[str, Any] | None:
        for pod in self.get_workload_pods(kind=kind, name=name, namespace=namespace):
            pod_name = str(pod.get("name") or "")
            if pod_name == previous_pod_name:
                continue
            if self._pod_is_healthy(pod):
                return pod
        return None

    def _next_poll_delay(self, *, attempt: int, base_delay: float, max_delay: float) -> float:
        if base_delay <= 0:
            return 0.0
        return min(base_delay * (2 ** max(attempt - 1, 0)), max_delay)

    def _rollout_timeout_message(
        self,
        *,
        kind: str,
        name: str,
        namespace: str,
        status: dict[str, Any] | None,
    ) -> str:
        if not status:
            return f"Timed out waiting for {kind} {namespace}/{name} rollout."
        return (
            f"Timed out waiting for {kind} {namespace}/{name} rollout; "
            f"last observed generation={status.get('generation')} observed_generation={status.get('observed_generation')} "
            f"updated_replicas={status.get('updated_replicas')} available_replicas={status.get('available_replicas')} "
            f"ready_replicas={status.get('ready_replicas')} desired_replicas={status.get('replicas')}."
        )

    def _pod_timeout_message(
        self,
        *,
        name: str,
        namespace: str,
        pod: dict[str, Any] | None,
        expected_absent: bool,
    ) -> str:
        if expected_absent:
            if pod:
                return (
                    f"Timed out waiting for pod {namespace}/{name} to disappear; "
                    f"last observed phase={pod.get('phase')} reason={pod.get('reason')}."
                )
            return f"Timed out waiting for pod {namespace}/{name} to disappear."
        if not pod:
            return f"Timed out waiting for pod {namespace}/{name} to recover."
        return (
            f"Timed out waiting for pod {namespace}/{name} to recover; "
            f"last observed phase={pod.get('phase')} reason={pod.get('reason')} "
            f"ready={self._pod_ready_summary(pod)}."
        )

    def _pod_ready_summary(self, pod: dict[str, Any]) -> str:
        statuses = pod.get("container_statuses") or []
        if not statuses:
            return "no containers"
        return ", ".join(
            f"{status.get('name', 'unknown')}={bool(status.get('ready'))}"
            for status in statuses
            if isinstance(status, dict)
        ) or "no containers"

    def _pod_is_healthy(self, pod: dict[str, Any]) -> bool:
        if str(pod.get("phase")) != "Running":
            return False
        statuses = pod.get("container_statuses", [])
        if not statuses:
            return False
        return all(bool(status.get("ready")) for status in statuses)

    def _serialize_pod(self, pod: Any) -> dict[str, Any]:
        statuses = getattr(getattr(pod, "status", None), "container_statuses", None) or []
        spec = getattr(pod, "spec", None)
        spec_containers = getattr(spec, "containers", None) or []
        spec_containers_by_name = {
            getattr(container, "name", None): container
            for container in spec_containers
            if getattr(container, "name", None)
        }
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
            container_name = getattr(status, "name", "unknown")
            spec_container = spec_containers_by_name.get(container_name)
            waiting = getattr(getattr(status, "state", None), "waiting", None)
            current_terminated = getattr(getattr(status, "state", None), "terminated", None)
            terminated = current_terminated or getattr(getattr(status, "last_state", None), "terminated", None)
            container_statuses.append(
                {
                    "name": container_name,
                    "restart_count": restart_count,
                    "waiting_reason": getattr(waiting, "reason", None),
                    "waiting_message": getattr(waiting, "message", None),
                    "terminated_reason": getattr(terminated, "reason", None),
                    "ready": getattr(status, "ready", False),
                    "image": getattr(status, "image", None) or getattr(spec_container, "image", None),
                    "image_pull_policy": getattr(spec_container, "image_pull_policy", None),
                }
            )
            if getattr(waiting, "reason", None):
                waiting_reasons.append(str(waiting.reason))

        return {
            "name": getattr(getattr(pod, "metadata", None), "name", "unknown"),
            "namespace": getattr(getattr(pod, "metadata", None), "namespace", "default"),
            "phase": getattr(getattr(pod, "status", None), "phase", "Unknown"),
            "reason": getattr(getattr(pod, "status", None), "reason", None),
            "message": getattr(getattr(pod, "status", None), "message", None),
            "created_at": self._serialize_datetime(getattr(getattr(pod, "metadata", None), "creation_timestamp", None)),
            "age_seconds": self._age_seconds(getattr(getattr(pod, "metadata", None), "creation_timestamp", None)),
            "node_name": getattr(spec, "node_name", None),
            "owner_kind": owner_kind,
            "owner_name": owner_name,
            "restart_count": total_restarts,
            "waiting_reasons": waiting_reasons,
            "container_statuses": container_statuses,
        }

    def _serialize_node(self, node: Any) -> dict[str, Any]:
        ready_condition = self._node_ready_condition(node)
        conditions = getattr(getattr(node, "status", None), "conditions", None) or []
        return {
            "name": getattr(getattr(node, "metadata", None), "name", "unknown"),
            "created_at": self._serialize_datetime(getattr(getattr(node, "metadata", None), "creation_timestamp", None)),
            "age_seconds": self._age_seconds(getattr(getattr(node, "metadata", None), "creation_timestamp", None)),
            "ready_status": getattr(ready_condition, "status", None),
            "ready_reason": getattr(ready_condition, "reason", None),
            "ready_message": getattr(ready_condition, "message", None),
            "unschedulable": bool(getattr(getattr(node, "spec", None), "unschedulable", False)),
            "conditions": [
                {
                    "type": getattr(condition, "type", None),
                    "status": getattr(condition, "status", None),
                    "reason": getattr(condition, "reason", None),
                    "message": getattr(condition, "message", None),
                }
                for condition in conditions
            ],
        }

    def _serialize_deployment(self, deployment: Any) -> dict[str, Any]:
        metadata = getattr(deployment, "metadata", None)
        spec = getattr(deployment, "spec", None)
        status = getattr(deployment, "status", None)
        template_spec = getattr(getattr(spec, "template", None), "spec", None)
        containers = getattr(template_spec, "containers", None) or []
        replicas = int(getattr(spec, "replicas", 1) or 1)
        updated_replicas = int(getattr(status, "updated_replicas", 0) or 0)
        ready_replicas = int(getattr(status, "ready_replicas", 0) or 0)
        available_replicas = int(getattr(status, "available_replicas", 0) or 0)
        unavailable_replicas = int(getattr(status, "unavailable_replicas", 0) or 0)
        return {
            "name": getattr(metadata, "name", "unknown"),
            "namespace": getattr(metadata, "namespace", "default"),
            "created_at": self._serialize_datetime(getattr(metadata, "creation_timestamp", None)),
            "age_seconds": self._age_seconds(getattr(metadata, "creation_timestamp", None)),
            "generation": int(getattr(metadata, "generation", 0) or 0),
            "observed_generation": int(getattr(status, "observed_generation", 0) or 0),
            "replicas": replicas,
            "updated_replicas": updated_replicas,
            "ready_replicas": ready_replicas,
            "available_replicas": available_replicas,
            "unavailable_replicas": unavailable_replicas,
            "containers": [self._serialize_container_spec(container) for container in containers],
            "stalled_seconds": self._deployment_stalled_seconds(
                created_at=getattr(metadata, "creation_timestamp", None),
                replicas=replicas,
                updated_replicas=updated_replicas,
            ),
        }

    def _deployment_stalled_seconds(self, *, created_at: Any, replicas: int, updated_replicas: int) -> int | None:
        if replicas <= 0 or updated_replicas >= replicas:
            return None
        return self._age_seconds(created_at)

    def _node_ready_condition(self, node: Any) -> Any | None:
        conditions = getattr(getattr(node, "status", None), "conditions", None) or []
        for condition in conditions:
            if getattr(condition, "type", None) == "Ready":
                return condition
        return None

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

    def _serialize_container_spec(self, container: Any) -> dict[str, Any]:
        resources = getattr(container, "resources", None)
        requests = getattr(resources, "requests", None) or {}
        limits = getattr(resources, "limits", None) or {}
        return {
            "name": getattr(container, "name", "unknown"),
            "resources": {
                "requests": dict(requests),
                "limits": dict(limits),
            },
        }

    def _serialize_datetime(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        return str(value)

    def _age_seconds(self, value: Any) -> int | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - value.astimezone(timezone.utc)
        return max(int(delta.total_seconds()), 0)
