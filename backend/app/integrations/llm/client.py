from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from ...models import Anomaly, RemediationPlan


class LLMClient:
    ABSENT_POD_OOM_EVENT_MAX_AGE_SECONDS = 300
    PENDING_POD_MIN_AGE_SECONDS = 300
    DEPLOYMENT_STALLED_MIN_AGE_SECONDS = 600

    def __init__(self, *, api_key: str, model: str = "gemini-1.5-flash", allow_workload_patches: bool = False) -> None:
        self.api_key = api_key
        self.model = model
        self.allow_workload_patches = allow_workload_patches
        self._client: Any | None = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def classify_events(
        self,
        *,
        events: list[dict[str, Any]],
        cluster_state: dict[str, Any],
        namespace: str,
    ) -> list[Anomaly]:
        anomalies: list[Anomaly] = []
        seen: set[tuple[str, str]] = set()
        pods_by_name = {
            str(pod.get("name") or ""): pod
            for pod in cluster_state.get("pods", [])
            if isinstance(pod, dict) and pod.get("name")
        }

        for event in events:
            anomaly = self._event_to_anomaly(event, namespace=namespace)
            if anomaly is None:
                continue
            pod = pods_by_name.get(str(anomaly.get("resource_name") or ""))
            if str(anomaly.get("resource_kind") or "") == "Pod":
                if pod is None:
                    if not self._keep_absent_pod_event(anomaly=anomaly, event=event):
                        continue
                    self._enrich_absent_seeded_oom_with_matching_workload(anomaly, pods_by_name)
                else:
                    self._enrich_anomaly_with_pod_owner(anomaly, pod)
            key = (anomaly["anomaly_type"], anomaly["resource_name"])
            if key in seen:
                continue
            anomalies.append(anomaly)
            seen.add(key)

        for pod in cluster_state.get("pods", []):
            anomaly = self._pod_to_anomaly(pod)
            if anomaly is None:
                continue
            key = (anomaly["anomaly_type"], anomaly["resource_name"])
            if key in seen:
                self._merge_evidence(anomalies, anomaly)
                continue
            anomalies.append(anomaly)
            seen.add(key)

        for node in cluster_state.get("nodes", []):
            anomaly = self._node_to_anomaly(node, namespace=namespace)
            if anomaly is None:
                continue
            key = (anomaly["anomaly_type"], anomaly["resource_name"])
            if key in seen:
                self._merge_evidence(anomalies, anomaly)
                continue
            anomalies.append(anomaly)
            seen.add(key)

        for deployment in cluster_state.get("deployments", []):
            anomaly = self._deployment_to_anomaly(deployment, namespace=namespace)
            if anomaly is None:
                continue
            key = (anomaly["anomaly_type"], anomaly["resource_name"])
            if key in seen:
                self._merge_evidence(anomalies, anomaly)
                continue
            anomalies.append(anomaly)
            seen.add(key)

        for metric in ((cluster_state.get("prometheus") or {}).get("metrics") if isinstance(cluster_state.get("prometheus"), dict) else []) or []:
            anomaly = self._prometheus_metric_to_anomaly(metric, namespace=namespace)
            if anomaly is None:
                continue
            pod = pods_by_name.get(str(anomaly.get("resource_name") or ""))
            if pod is not None:
                self._enrich_anomaly_with_pod_owner(anomaly, pod)
            key = (anomaly["anomaly_type"], anomaly["resource_name"])
            if key in seen:
                self._merge_evidence(anomalies, anomaly)
                continue
            anomalies.append(anomaly)
            seen.add(key)

        return self._drop_shadowed_anomalies(anomalies)

    def diagnose(
        self,
        *,
        anomaly: Anomaly,
        logs: str,
        pod_description: dict[str, Any],
    ) -> str:
        fallback = self._fallback_diagnosis(anomaly=anomaly, logs=logs, pod_description=pod_description)
        prompt = (
            "You are diagnosing a Kubernetes incident. Summarize the likely root cause, "
            "cite evidence, and keep the answer short.\n"
            f"Anomaly: {json.dumps(anomaly)}\n"
            f"Pod description: {json.dumps(pod_description)}\n"
            f"Logs:\n{logs[:4000]}"
        )
        return self._invoke_text(prompt=prompt, fallback=fallback)

    def plan_remediation(self, *, anomaly: Anomaly, diagnosis: str) -> RemediationPlan:
        anomaly_type = anomaly.get("anomaly_type", "Unknown")
        resource_name = anomaly.get("resource_name", "unknown")
        namespace = anomaly.get("namespace", "default")

        base_plans: dict[str, RemediationPlan] = {
            "CrashLoopBackOff": {
                "action": "restart_pod",
                "target_kind": anomaly.get("resource_kind", "Pod"),
                "target_name": resource_name,
                "namespace": namespace,
                "parameters": {
                    "target_workload_kind": anomaly.get("workload_kind", "Pod"),
                    "target_workload_name": anomaly.get("workload_name", resource_name),
                },
                "confidence": 0.86,
                "blast_radius": "low",
                "reason": diagnosis,
                "requires_human": False,
            },
            "OOMKilled": {
                "action": "patch_pod",
                "target_kind": anomaly.get("resource_kind", "Pod"),
                "target_name": resource_name,
                "namespace": namespace,
                "parameters": {
                    "recommendation": self._oomkill_recommendation(anomaly),
                    "suggested_memory_factor": 1.5,
                    "suggested_follow_up": self._workload_follow_up(anomaly),
                    "target_workload_kind": anomaly.get("workload_kind", "Pod"),
                    "target_workload_name": anomaly.get("workload_name", resource_name),
                    "patch": self._oomkill_patch(anomaly),
                },
                "confidence": 0.65,
                "blast_radius": "medium",
                "reason": diagnosis,
                "requires_human": True,
            },
            "PendingPod": {
                "action": "notify_only",
                "target_kind": anomaly.get("resource_kind", "Pod"),
                "target_name": resource_name,
                "namespace": namespace,
                "parameters": {
                    "recommendation": self._pending_pod_recommendation(anomaly),
                    "scheduling_hints": anomaly.get("evidence", []),
                    "target_workload_kind": anomaly.get("workload_kind", "Pod"),
                    "target_workload_name": anomaly.get("workload_name", resource_name),
                },
                "confidence": 0.6,
                "blast_radius": "medium",
                "reason": diagnosis,
                "requires_human": True,
            },
            "ImagePullBackOff": {
                "action": "notify_only",
                "target_kind": anomaly.get("resource_kind", "Pod"),
                "target_name": resource_name,
                "namespace": namespace,
                "parameters": {
                    "recommendation": self._image_pull_recommendation(anomaly),
                },
                "confidence": 0.5,
                "blast_radius": "medium",
                "reason": diagnosis,
                "requires_human": True,
            },
            "CPUThrottling": {
                "action": "patch_pod",
                "target_kind": anomaly.get("resource_kind", "Pod"),
                "target_name": resource_name,
                "namespace": namespace,
                "parameters": {
                    "recommendation": self._cpu_throttling_recommendation(anomaly),
                    "observed_ratio": anomaly.get("metrics", {}).get("cpu_throttling_ratio"),
                    "suggested_cpu_factor": 1.5,
                    "target_workload_kind": anomaly.get("workload_kind", "Pod"),
                    "target_workload_name": anomaly.get("workload_name", resource_name),
                    "patch": self._cpu_throttling_patch(anomaly),
                },
                "confidence": 0.58,
                "blast_radius": "medium",
                "reason": diagnosis,
                "requires_human": True,
            },
            "EvictedPod": {
                "action": "delete_pod",
                "target_kind": anomaly.get("resource_kind", "Pod"),
                "target_name": resource_name,
                "namespace": namespace,
                "parameters": {},
                "confidence": 0.82,
                "blast_radius": "low",
                "reason": diagnosis,
                "requires_human": False,
            },
            "DeploymentStalled": {
                "action": "escalate_to_human",
                "target_kind": anomaly.get("resource_kind", "Deployment"),
                "target_name": resource_name,
                "namespace": namespace,
                "parameters": {},
                "confidence": 0.51,
                "blast_radius": "high",
                "reason": diagnosis,
                "requires_human": True,
            },
            "NodeNotReady": {
                "action": "escalate_to_human",
                "target_kind": anomaly.get("resource_kind", "Node"),
                "target_name": resource_name,
                "namespace": namespace,
                "parameters": {},
                "confidence": 0.33,
                "blast_radius": "high",
                "reason": diagnosis,
                "requires_human": True,
            },
        }

        return base_plans.get(
            anomaly_type,
            {
                "action": "collect_more_evidence",
                "target_kind": anomaly.get("resource_kind", "Pod"),
                "target_name": resource_name,
                "namespace": namespace,
                "parameters": {},
                "confidence": 0.4,
                "blast_radius": "medium",
                "reason": diagnosis,
                "requires_human": True,
            },
        )

    def explain(
        self,
        *,
        anomaly: Anomaly | None,
        diagnosis: str,
        plan: RemediationPlan | None,
        approved: bool | None,
        result: str,
    ) -> str:
        fallback = self._fallback_explanation(
            anomaly=anomaly,
            diagnosis=diagnosis,
            plan=plan,
            approved=approved,
            result=result,
        )
        prompt = (
            "Explain this Kubernetes incident outcome in plain English for a human operator.\n"
            f"Anomaly: {json.dumps(anomaly or {})}\n"
            f"Diagnosis: {diagnosis}\n"
            f"Plan: {json.dumps(plan or {})}\n"
            f"Approved: {approved}\n"
            f"Result: {result}"
        )
        return self._invoke_text(prompt=prompt, fallback=fallback)

    def _invoke_text(self, *, prompt: str, fallback: str) -> str:
        if not self.is_configured():
            return fallback

        try:
            if self._client is None:
                from langchain_google_genai import ChatGoogleGenerativeAI

                self._client = ChatGoogleGenerativeAI(
                    model=self.model,
                    google_api_key=self.api_key,
                    temperature=0.2,
                )

            response = self._client.invoke(prompt)
            content = getattr(response, "content", "")
            if isinstance(content, list):
                return " ".join(str(item) for item in content) or fallback
            text = str(content).strip()
            return text or fallback
        except Exception:
            return fallback

    def _event_to_anomaly(self, event: dict[str, Any], namespace: str) -> Anomaly | None:
        reason = str(event.get("reason") or "")
        message = str(event.get("message") or "")
        resource_name = str(event.get("resource_name") or "unknown")
        resource_kind = str(event.get("resource_kind") or "Pod")
        combined = f"{reason} {message}".lower()

        if "oomkilled" in combined:
            return self._build_anomaly(
                anomaly_type="OOMKilled",
                severity="high",
                resource_kind=resource_kind,
                resource_name=resource_name,
                namespace=namespace,
                summary=message or "Pod terminated because it ran out of memory.",
                confidence=0.83,
            )

        if "crashloopbackoff" in combined or reason == "BackOff":
            return self._build_anomaly(
                anomaly_type="CrashLoopBackOff",
                severity="high",
                resource_kind=resource_kind,
                resource_name=resource_name,
                namespace=namespace,
                summary=message or "Pod is repeatedly crashing.",
                confidence=0.87,
            )

        if reason == "FailedScheduling" or "insufficient" in combined:
            return self._build_anomaly(
                anomaly_type="PendingPod",
                severity="medium",
                resource_kind=resource_kind,
                resource_name=resource_name,
                namespace=namespace,
                summary=message or "Pod could not be scheduled.",
                confidence=0.76,
                evidence=[reason or "FailedScheduling", message or "Scheduling constraints prevented placement."],
            )

        if "imagepullbackoff" in combined or "errimagepull" in combined:
            return self._build_anomaly(
                anomaly_type="ImagePullBackOff",
                severity="medium",
                resource_kind=resource_kind,
                resource_name=resource_name,
                namespace=namespace,
                summary=message or "Image pull failed for this pod.",
                confidence=0.74,
                evidence=[reason or "ImagePullBackOff", message or "Image pull failed for the container image."],
            )

        if "evicted" in combined:
            return self._build_anomaly(
                anomaly_type="EvictedPod",
                severity="low",
                resource_kind=resource_kind,
                resource_name=resource_name,
                namespace=namespace,
                summary=message or "Pod was evicted from its node.",
                confidence=0.79,
                evidence=[reason or "Evicted", message or "Pod was evicted by the kubelet."] ,
            )

        return None

    def _pod_to_anomaly(self, pod: dict[str, Any]) -> Anomaly | None:
        name = str(pod.get("name") or "unknown")
        namespace = str(pod.get("namespace") or "default")
        phase = str(pod.get("phase") or "Unknown")
        restart_count = int(pod.get("restart_count") or 0)
        waiting_reasons = [str(reason) for reason in pod.get("waiting_reasons", [])]

        for status in pod.get("container_statuses", []):
            terminated_reason = str(status.get("terminated_reason") or "")
            if terminated_reason == "OOMKilled":
                return self._build_anomaly(
                    anomaly_type="OOMKilled",
                    severity="high",
                    resource_kind="Pod",
                    resource_name=name,
                    namespace=namespace,
                    workload_kind=str(pod.get("owner_kind") or "Pod"),
                    workload_name=str(pod.get("owner_name") or name),
                    summary=f"Container in pod {name} was OOMKilled.",
                    confidence=0.82,
                )

        if restart_count > 3:
            return self._build_anomaly(
                anomaly_type="CrashLoopBackOff",
                severity="high",
                resource_kind="Pod",
                resource_name=name,
                namespace=namespace,
                workload_kind=str(pod.get("owner_kind") or "Pod"),
                workload_name=str(pod.get("owner_name") or name),
                summary=f"Pod {name} restarted {restart_count} times.",
                confidence=0.84,
            )

        if phase == "Pending" and self._pending_pod_old_enough(pod):
            return self._build_anomaly(
                anomaly_type="PendingPod",
                severity="medium",
                resource_kind="Pod",
                resource_name=name,
                namespace=namespace,
                workload_kind=str(pod.get("owner_kind") or "Pod"),
                workload_name=str(pod.get("owner_name") or name),
                summary=f"Pod {name} is still pending.",
                confidence=0.68,
                evidence=self._pending_pod_evidence(pod),
            )

        if any(reason == "ImagePullBackOff" for reason in waiting_reasons):
            return self._build_anomaly(
                anomaly_type="ImagePullBackOff",
                severity="medium",
                resource_kind="Pod",
                resource_name=name,
                namespace=namespace,
                workload_kind=str(pod.get("owner_kind") or "Pod"),
                workload_name=str(pod.get("owner_name") or name),
                summary=f"Pod {name} is in ImagePullBackOff.",
                confidence=0.78,
                evidence=[
                    f"pod phase: {phase}",
                    "waiting reason: ImagePullBackOff",
                ],
            )

        if str(pod.get("reason") or "") == "Evicted":
            return self._build_anomaly(
                anomaly_type="EvictedPod",
                severity="low",
                resource_kind="Pod",
                resource_name=name,
                namespace=namespace,
                workload_kind=str(pod.get("owner_kind") or "Pod"),
                workload_name=str(pod.get("owner_name") or name),
                summary=f"Pod {name} was evicted from its node.",
                confidence=0.8,
                evidence=[
                    "pod status reason: Evicted",
                    f"pod phase: {phase}",
                ],
            )

        return None

    def _prometheus_metric_to_anomaly(self, metric: dict[str, Any], *, namespace: str) -> Anomaly | None:
        try:
            ratio = float(metric.get("ratio") or 0.0)
            threshold = float(metric.get("threshold") or 0.5)
        except (TypeError, ValueError):
            return None
        if ratio <= threshold:
            return None

        pod_name = str(metric.get("pod") or "unknown")
        anomaly = self._build_anomaly(
            anomaly_type="CPUThrottling",
            severity="medium",
            resource_kind="Pod",
            resource_name=pod_name,
            namespace=str(metric.get("namespace") or namespace),
            summary=f"Pod {pod_name} is CPU throttled above the configured threshold.",
            confidence=min(0.95, 0.6 + min(ratio, 1.0) * 0.3),
            evidence=[
                f"cpu throttling ratio: {ratio:.2f}",
                f"cpu throttling threshold: {threshold:.2f}",
            ],
        )
        anomaly["metrics"] = {
            "cpu_throttling_ratio": ratio,
            "cpu_throttling_threshold": threshold,
        }
        return anomaly

    def _drop_shadowed_anomalies(self, anomalies: list[Anomaly]) -> list[Anomaly]:
        oomkilled_resources = {
            str(anomaly.get("resource_name") or "")
            for anomaly in anomalies
            if anomaly.get("anomaly_type") == "OOMKilled"
        }
        if not oomkilled_resources:
            return anomalies

        return [
            anomaly
            for anomaly in anomalies
            if not (
                anomaly.get("anomaly_type") == "CrashLoopBackOff"
                and str(anomaly.get("resource_name") or "") in oomkilled_resources
            )
        ]

    def _keep_absent_pod_event(self, *, anomaly: Anomaly, event: dict[str, Any]) -> bool:
        if bool(event.get("seeded")):
            return True
        if anomaly.get("anomaly_type") != "OOMKilled":
            return False
        age_seconds = self._event_age_seconds(event)
        return age_seconds is not None and age_seconds <= self.ABSENT_POD_OOM_EVENT_MAX_AGE_SECONDS

    def _event_age_seconds(self, event: dict[str, Any]) -> float | None:
        last_timestamp = str(event.get("last_timestamp") or "").strip()
        if not last_timestamp:
            return None
        try:
            parsed = datetime.fromisoformat(last_timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return abs((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())

    def _node_to_anomaly(self, node: dict[str, Any], *, namespace: str) -> Anomaly | None:
        ready_status = str(node.get("ready_status") or "")
        if ready_status != "False":
            return None

        name = str(node.get("name") or "unknown")
        reason = str(node.get("ready_reason") or "")
        message = str(node.get("ready_message") or "")
        evidence = ["node Ready condition is False"]
        if reason:
            evidence.append(f"ready reason: {reason}")
        if message:
            evidence.append(f"ready message: {message}")
        if node.get("unschedulable"):
            evidence.append("node is marked unschedulable")
        for condition in node.get("conditions", []):
            if not isinstance(condition, dict):
                continue
            condition_type = str(condition.get("type") or "")
            condition_status = str(condition.get("status") or "")
            if condition_type == "Ready" or condition_status != "True":
                continue
            condition_reason = str(condition.get("reason") or "")
            condition_message = str(condition.get("message") or "")
            detail = f"node condition {condition_type}=True"
            if condition_reason:
                detail = f"{detail} ({condition_reason})"
            if condition_message:
                detail = f"{detail}: {condition_message}"
            evidence.append(detail)

        return self._build_anomaly(
            anomaly_type="NodeNotReady",
            severity="critical",
            resource_kind="Node",
            resource_name=name,
            namespace=namespace,
            workload_kind="Node",
            workload_name=name,
            summary=f"Node {name} is reporting NotReady.",
            confidence=0.81,
            evidence=evidence,
        )

    def _deployment_to_anomaly(self, deployment: dict[str, Any], *, namespace: str) -> Anomaly | None:
        replicas = int(deployment.get("replicas") or 0)
        updated_replicas = int(deployment.get("updated_replicas") or 0)
        stalled_seconds = deployment.get("stalled_seconds")
        if replicas <= 0 or updated_replicas >= replicas:
            return None
        if not isinstance(stalled_seconds, int) or stalled_seconds < self.DEPLOYMENT_STALLED_MIN_AGE_SECONDS:
            return None

        name = str(deployment.get("name") or "unknown")
        return self._build_anomaly(
            anomaly_type="DeploymentStalled",
            severity="high",
            resource_kind="Deployment",
            resource_name=name,
            namespace=str(deployment.get("namespace") or namespace),
            workload_kind="Deployment",
            workload_name=name,
            summary=f"Deployment {name} has not finished rolling out.",
            confidence=0.8,
            evidence=[
                f"updated replicas: {updated_replicas}",
                f"desired replicas: {replicas}",
                f"deployment stalled seconds: {stalled_seconds}",
            ],
        )

    def _build_anomaly(
        self,
        *,
        anomaly_type: str,
        severity: str,
        resource_kind: str,
        resource_name: str,
        namespace: str,
        workload_kind: str | None = None,
        workload_name: str | None = None,
        summary: str,
        confidence: float,
        evidence: list[str] | None = None,
    ) -> Anomaly:
        return {
            "anomaly_type": anomaly_type,
            "severity": severity,
            "resource_kind": resource_kind,
            "resource_name": resource_name,
            "namespace": namespace,
            "workload_kind": workload_kind or resource_kind,
            "workload_name": workload_name or resource_name,
            "summary": summary,
            "confidence": confidence,
            "evidence": evidence or [summary],
        }

    def _merge_evidence(self, anomalies: list[Anomaly], incoming: Anomaly) -> None:
        for anomaly in anomalies:
            if anomaly.get("anomaly_type") != incoming.get("anomaly_type"):
                continue
            if anomaly.get("resource_name") != incoming.get("resource_name"):
                continue

            current_evidence = list(anomaly.get("evidence", []))
            for item in incoming.get("evidence", []):
                if item not in current_evidence:
                    current_evidence.append(item)
            anomaly["evidence"] = current_evidence
            anomaly["confidence"] = max(float(anomaly.get("confidence", 0.0)), float(incoming.get("confidence", 0.0)))
            incoming_workload_kind = incoming.get("workload_kind")
            incoming_workload_name = incoming.get("workload_name")
            current_workload_kind = anomaly.get("workload_kind")
            current_workload_name = anomaly.get("workload_name")
            current_resource_name = anomaly.get("resource_name")
            if incoming_workload_kind and incoming_workload_kind != "Pod":
                anomaly["workload_kind"] = incoming_workload_kind
            elif not current_workload_kind:
                anomaly["workload_kind"] = incoming_workload_kind or current_workload_kind
            if incoming_workload_name and incoming_workload_name != current_resource_name:
                anomaly["workload_name"] = incoming_workload_name
            elif not current_workload_name:
                anomaly["workload_name"] = incoming_workload_name or current_workload_name
            return

    def _enrich_anomaly_with_pod_owner(self, anomaly: Anomaly, pod: dict[str, Any]) -> None:
        owner_kind = str(pod.get("owner_kind") or "")
        owner_name = str(pod.get("owner_name") or "")
        if owner_kind:
            anomaly["workload_kind"] = owner_kind
        if owner_name:
            anomaly["workload_name"] = owner_name

    def _enrich_absent_seeded_oom_with_matching_workload(self, anomaly: Anomaly, pods_by_name: dict[str, dict[str, Any]]) -> None:
        if anomaly.get("anomaly_type") != "OOMKilled":
            return
        if anomaly.get("workload_kind") and anomaly.get("workload_kind") != "Pod":
            return
        resource_name = str(anomaly.get("resource_name") or "")
        if not resource_name:
            return
        candidates = [
            pod
            for pod in pods_by_name.values()
            if str(pod.get("owner_name") or "") == resource_name
            or str(pod.get("name") or "").startswith(f"{resource_name}-")
        ]
        for pod in candidates:
            self._enrich_anomaly_with_pod_owner(anomaly, pod)
            return

    def _pending_pod_evidence(self, pod: dict[str, Any]) -> list[str]:
        evidence = [f"pod phase: {pod.get('phase', 'Unknown')}"]
        reason = str(pod.get("reason") or "")
        age_seconds = pod.get("age_seconds")
        if reason:
            evidence.append(f"status reason: {reason}")
        if isinstance(age_seconds, int):
            evidence.append(f"pending age seconds: {age_seconds}")
        return evidence

    def _pending_pod_old_enough(self, pod: dict[str, Any]) -> bool:
        age_seconds = pod.get("age_seconds")
        return isinstance(age_seconds, int) and age_seconds >= self.PENDING_POD_MIN_AGE_SECONDS

    def _pending_pod_recommendation(self, anomaly: Anomaly) -> str:
        evidence_text = " ".join(str(item) for item in anomaly.get("evidence", []))
        lower = evidence_text.lower()
        workload = self._workload_label(anomaly)
        if "insufficient memory" in lower:
            return f"Reduce memory requests for {workload} or free cluster memory in the target namespace before retrying scheduling."
        if "insufficient cpu" in lower:
            return f"Reduce CPU requests for {workload} or free CPU capacity before retrying scheduling."
        if "taint" in lower:
            return f"Add the required toleration for {workload} or schedule it onto a compatible node pool."
        if "affinity" in lower or "selector" in lower:
            return f"Review node selectors or affinity rules for {workload} because they currently exclude all available nodes."
        return f"Review scheduling events, resource requests, selectors, and tolerations for {workload} before retrying the pod."

    def _cpu_throttling_recommendation(self, anomaly: Anomaly) -> str:
        workload = self._workload_label(anomaly)
        ratio = ((anomaly.get("metrics") or {}).get("cpu_throttling_ratio") if isinstance(anomaly.get("metrics"), dict) else None)
        if isinstance(ratio, (float, int)):
            return f"Increase the CPU limit for {workload} by roughly 50% and verify the throttling ratio drops below the threshold; Prometheus reports {float(ratio):.2f}."
        return f"Review CPU requests and limits for {workload}; Prometheus indicates sustained CPU throttling."

    def _cpu_throttling_patch(self, anomaly: Anomaly) -> dict[str, Any] | None:
        if not self.allow_workload_patches:
            return None
        workload_kind = str(anomaly.get("workload_kind") or "Pod")
        if workload_kind != "Deployment":
            return None
        return {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "app",
                                "resources": {
                                    "limits": {"cpu": "300m"},
                                },
                            }
                        ]
                    }
                }
            }
        }

    def _image_pull_recommendation(self, anomaly: Anomaly) -> str:
        workload = self._workload_label(anomaly)
        return f"Inspect the image reference, registry credentials, and pull policy for {workload}, then alert a human operator with the failing image details."

    def _oomkill_recommendation(self, anomaly: Anomaly) -> str:
        workload = self._workload_label(anomaly)
        return f"Increase the memory limit for {workload} by roughly 50% and then restart the affected pod or rollout."

    def _oomkill_patch(self, anomaly: Anomaly) -> dict[str, Any] | None:
        if not self.allow_workload_patches:
            return None
        workload_kind = str(anomaly.get("workload_kind") or "Pod")
        if workload_kind != "Deployment":
            return None
        return {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "memory-hog",
                                "resources": {
                                    "limits": {"memory": "96Mi"},
                                    "requests": {"memory": "48Mi"},
                                },
                            }
                        ]
                    }
                }
            }
        }

    def _workload_follow_up(self, anomaly: Anomaly) -> str:
        workload_kind = str(anomaly.get("workload_kind") or "Pod")
        workload_name = str(anomaly.get("workload_name") or anomaly.get("resource_name") or "unknown")
        if workload_kind in {"Deployment", "StatefulSet", "DaemonSet"}:
            return f"Patch {workload_kind} {workload_name} and trigger a rollout restart if needed."
        return f"Patch the owning workload for {workload_name} and restart the affected pod if needed."

    def _workload_label(self, anomaly: Anomaly) -> str:
        workload_kind = str(anomaly.get("workload_kind") or anomaly.get("resource_kind") or "Pod")
        workload_name = str(anomaly.get("workload_name") or anomaly.get("resource_name") or "unknown")
        return f"{workload_kind} `{workload_name}`"

    def _fallback_diagnosis(
        self,
        *,
        anomaly: Anomaly,
        logs: str,
        pod_description: dict[str, Any],
    ) -> str:
        evidence = anomaly.get("summary", "No anomaly summary provided.")
        if logs and "Unable to fetch logs" not in logs:
            evidence = f"{evidence} Recent logs were collected for review."
        if pod_description.get("error"):
            evidence = f"{evidence} Pod inspection was limited: {pod_description['error']}"
        return (
            f"Likely root cause for {anomaly.get('resource_name', 'unknown')} is "
            f"{anomaly.get('anomaly_type', 'an anomalous condition')}. Evidence: {evidence}"
        )

    def _fallback_explanation(
        self,
        *,
        anomaly: Anomaly | None,
        diagnosis: str,
        plan: RemediationPlan | None,
        approved: bool | None,
        result: str,
    ) -> str:
        anomaly_name = anomaly.get("anomaly_type", "Unknown") if anomaly else "Unknown"
        action = plan.get("action", "notify_only") if plan else "notify_only"
        approval_text = "approved" if approved else "not approved"
        if approved is None:
            approval_text = "not yet approved"
        return (
            f"Detected {anomaly_name}. Diagnosis: {diagnosis} "
            f"Planned action: {action}. Approval status: {approval_text}. Result: {result}"
        )
