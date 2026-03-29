from __future__ import annotations

import json
from typing import Any

from ...models import Anomaly, RemediationPlan


class LLMClient:
    def __init__(self, *, api_key: str, model: str = "gemini-1.5-flash") -> None:
        self.api_key = api_key
        self.model = model
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

        for event in events:
            anomaly = self._event_to_anomaly(event, namespace=namespace)
            if anomaly is None:
                continue
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
                    "recommendation": "Increase memory limit on the owning workload by roughly 50% and then restart the pod.",
                    "suggested_memory_factor": 1.5,
                    "suggested_follow_up": "rollout restart owning deployment or restart the pod after patching limits",
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
                "parameters": {},
                "confidence": 0.55,
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
                summary=f"Pod {name} restarted {restart_count} times.",
                confidence=0.84,
            )

        if phase == "Pending":
            return self._build_anomaly(
                anomaly_type="PendingPod",
                severity="medium",
                resource_kind="Pod",
                resource_name=name,
                namespace=namespace,
                summary=f"Pod {name} is still pending.",
                confidence=0.68,
            )

        if any(reason == "ImagePullBackOff" for reason in waiting_reasons):
            return self._build_anomaly(
                anomaly_type="ImagePullBackOff",
                severity="medium",
                resource_kind="Pod",
                resource_name=name,
                namespace=namespace,
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
                    summary=f"Container in pod {name} was OOMKilled.",
                    confidence=0.82,
                )

        return None

    def _build_anomaly(
        self,
        *,
        anomaly_type: str,
        severity: str,
        resource_kind: str,
        resource_name: str,
        namespace: str,
        summary: str,
        confidence: float,
    ) -> Anomaly:
        return {
            "anomaly_type": anomaly_type,
            "severity": severity,
            "resource_kind": resource_kind,
            "resource_name": resource_name,
            "namespace": namespace,
            "summary": summary,
            "confidence": confidence,
            "evidence": [summary],
        }

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
            evidence = f"{evidence} Pod describe output was limited: {pod_description['error']}"
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
