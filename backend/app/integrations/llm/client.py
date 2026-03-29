from __future__ import annotations

import json
from typing import Any

from ...models import Anomaly, RemediationPlan


class LLMClient:
    PENDING_POD_MIN_AGE_SECONDS = 300

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
            if pod is not None:
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

        return anomalies

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
                "parameters": {},
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
                "parameters": {},
                "confidence": 0.5,
                "blast_radius": "medium",
                "reason": diagnosis,
                "requires_human": True,
            },
            "CPUThrottling": {
                "action": "collect_more_evidence",
                "target_kind": anomaly.get("resource_kind", "Pod"),
                "target_name": resource_name,
                "namespace": namespace,
                "parameters": {},
                "confidence": 0.45,
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
            )

        return None

    def _pod_to_anomaly(self, pod: dict[str, Any]) -> Anomaly | None:
        name = str(pod.get("name") or "unknown")
        namespace = str(pod.get("namespace") or "default")
        phase = str(pod.get("phase") or "Unknown")
        restart_count = int(pod.get("restart_count") or 0)
        waiting_reasons = [str(reason) for reason in pod.get("waiting_reasons", [])]

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
            )

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

        return None

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

        return self._build_anomaly(
            anomaly_type="NodeNotReady",
            severity="high",
            resource_kind="Node",
            resource_name=name,
            namespace=namespace,
            workload_kind="Node",
            workload_name=name,
            summary=f"Node {name} is reporting NotReady.",
            confidence=0.81,
            evidence=evidence,
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
