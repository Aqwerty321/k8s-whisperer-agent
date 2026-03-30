from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any

from ...models import Anomaly, RemediationPlan


class LLMClient:
    ABSENT_POD_OOM_EVENT_MAX_AGE_SECONDS = 300
    PENDING_POD_MIN_AGE_SECONDS = 300
    DEPLOYMENT_STALLED_MIN_AGE_SECONDS = 600
    VALID_ANOMALY_TYPES = {
        "CrashLoopBackOff",
        "OOMKilled",
        "PendingPod",
        "ImagePullBackOff",
        "CPUThrottling",
        "EvictedPod",
        "DeploymentStalled",
        "NodeNotReady",
    }
    VALID_SEVERITIES = {"low", "medium", "high", "critical"}

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
        anomalies = self._classify_events_heuristic(
            events=events,
            cluster_state=cluster_state,
            namespace=namespace,
        )
        self._merge_llm_detected_anomalies(
            anomalies=anomalies,
            events=events,
            cluster_state=cluster_state,
            namespace=namespace,
        )
        return self._drop_shadowed_anomalies(anomalies)

    def _classify_events_heuristic(
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
        deployments_by_name = {
            str(deployment.get("name") or ""): deployment
            for deployment in cluster_state.get("deployments", [])
            if isinstance(deployment, dict) and deployment.get("name")
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
                    self._enrich_anomaly_with_container_details(anomaly, pod)
            self._enrich_anomaly_with_workload_resources(anomaly, deployments_by_name)
            key = (anomaly["anomaly_type"], anomaly["resource_name"])
            if key in seen:
                continue
            anomalies.append(anomaly)
            seen.add(key)

        for pod in cluster_state.get("pods", []):
            anomaly = self._pod_to_anomaly(pod)
            if anomaly is None:
                continue
            self._enrich_anomaly_with_container_details(anomaly, pod)
            self._enrich_anomaly_with_workload_resources(anomaly, deployments_by_name)
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
                self._enrich_anomaly_with_container_details(anomaly, pod)
            self._enrich_anomaly_with_workload_resources(anomaly, deployments_by_name)
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
                    "current_memory_limit": self._oomkill_memory_value(anomaly, "current_memory_limit"),
                    "current_memory_request": self._oomkill_memory_value(anomaly, "current_memory_request"),
                    "suggested_memory_limit": self._oomkill_scaled_memory_value(anomaly, "current_memory_limit"),
                    "suggested_memory_request": self._oomkill_scaled_memory_value(anomaly, "current_memory_request"),
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
                    "throttling_threshold": anomaly.get("metrics", {}).get("cpu_throttling_threshold"),
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
            response = self._get_client().invoke(prompt)
            content = getattr(response, "content", "")
            if isinstance(content, list):
                return " ".join(str(item) for item in content) or fallback
            text = str(content).strip()
            return text or fallback
        except Exception:
            return fallback

    def _get_client(self) -> Any:
        if self._client is None:
            from langchain_google_genai import ChatGoogleGenerativeAI

            self._client = ChatGoogleGenerativeAI(
                model=self.model,
                google_api_key=self.api_key,
                temperature=0.2,
            )
        return self._client

    def _invoke_json(self, *, prompt: str) -> Any | None:
        if not self.is_configured():
            return None

        try:
            response = self._get_client().invoke(prompt)
            content = getattr(response, "content", "")
            if isinstance(content, list):
                text = " ".join(str(item) for item in content)
            else:
                text = str(content)
            return self._extract_json_payload(text)
        except Exception:
            return None

    def _extract_json_payload(self, text: str) -> Any | None:
        raw = str(text or "").strip()
        if not raw:
            return None
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = "\n".join(part for part in parts if part and not part.lower().startswith("json")).strip()

        for start_char, end_char in (("{", "}"), ("[", "]")):
            start = raw.find(start_char)
            end = raw.rfind(end_char)
            if start == -1 or end == -1 or end < start:
                continue
            snippet = raw[start : end + 1]
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                continue
        return None

    def _merge_llm_detected_anomalies(
        self,
        *,
        anomalies: list[Anomaly],
        events: list[dict[str, Any]],
        cluster_state: dict[str, Any],
        namespace: str,
    ) -> None:
        if not self.is_configured():
            return

        llm_response = self._invoke_json(
            prompt=self._build_detection_prompt(events=events, cluster_state=cluster_state, namespace=namespace)
        )
        if not isinstance(llm_response, dict):
            return

        raw_anomalies = llm_response.get("anomalies")
        if not isinstance(raw_anomalies, list) or not raw_anomalies:
            return

        pods_by_name = {
            str(pod.get("name") or ""): pod
            for pod in cluster_state.get("pods", [])
            if isinstance(pod, dict) and pod.get("name")
        }
        deployments_by_name = {
            str(deployment.get("name") or ""): deployment
            for deployment in cluster_state.get("deployments", [])
            if isinstance(deployment, dict) and deployment.get("name")
        }
        seen = {
            (str(anomaly.get("anomaly_type") or ""), str(anomaly.get("resource_name") or ""))
            for anomaly in anomalies
        }

        for raw_anomaly in raw_anomalies:
            anomaly = self._normalize_llm_anomaly(
                raw_anomaly,
                namespace=namespace,
                pods_by_name=pods_by_name,
                deployments_by_name=deployments_by_name,
            )
            if anomaly is None:
                continue
            key = (str(anomaly.get("anomaly_type") or ""), str(anomaly.get("resource_name") or ""))
            if key in seen:
                self._merge_evidence(anomalies, anomaly)
                continue
            anomalies.append(anomaly)
            seen.add(key)

    def _build_detection_prompt(
        self,
        *,
        events: list[dict[str, Any]],
        cluster_state: dict[str, Any],
        namespace: str,
    ) -> str:
        payload = {
            "namespace": namespace,
            "events": events[:25],
            "pods": (cluster_state.get("pods") or [])[:25],
            "deployments": (cluster_state.get("deployments") or [])[:15],
            "nodes": (cluster_state.get("nodes") or [])[:15],
            "prometheus": cluster_state.get("prometheus") or {},
        }
        return (
            "Classify Kubernetes incident anomalies from the supplied events and cluster snapshot. "
            "Return strict JSON only with the shape "
            '{"anomalies":[{"anomaly_type":"...","resource_name":"...","resource_kind":"...","namespace":"...","severity":"...","summary":"...","confidence":0.0,"evidence":["..."]}]}. '
            f"Only use these anomaly types: {sorted(self.VALID_ANOMALY_TYPES)}. "
            "Only include anomalies that are directly supported by the payload. Do not invent resources. "
            "If nothing is clearly wrong, return {\"anomalies\":[]}.\n"
            f"Payload: {json.dumps(payload, default=str)[:12000]}"
        )

    def _normalize_llm_anomaly(
        self,
        raw_anomaly: Any,
        *,
        namespace: str,
        pods_by_name: dict[str, dict[str, Any]],
        deployments_by_name: dict[str, dict[str, Any]],
    ) -> Anomaly | None:
        if not isinstance(raw_anomaly, dict):
            return None

        anomaly_type = str(raw_anomaly.get("anomaly_type") or "").strip()
        if anomaly_type not in self.VALID_ANOMALY_TYPES:
            return None

        resource_name = str(raw_anomaly.get("resource_name") or "").strip()
        if not resource_name:
            return None

        resource_kind = str(raw_anomaly.get("resource_kind") or self._default_resource_kind_for_anomaly(anomaly_type)).strip() or "Pod"
        severity = str(raw_anomaly.get("severity") or self._default_severity_for_anomaly(anomaly_type)).strip().lower()
        if severity not in self.VALID_SEVERITIES:
            severity = self._default_severity_for_anomaly(anomaly_type)

        summary = str(raw_anomaly.get("summary") or "").strip() or f"{anomaly_type} detected for {resource_name}."
        confidence = self._normalize_confidence(raw_anomaly.get("confidence"))
        evidence = self._normalize_evidence(raw_anomaly.get("evidence"), summary=summary)

        anomaly = self._build_anomaly(
            anomaly_type=anomaly_type,
            severity=severity,
            resource_kind=resource_kind,
            resource_name=resource_name,
            namespace=str(raw_anomaly.get("namespace") or namespace),
            workload_kind=str(raw_anomaly.get("workload_kind") or resource_kind),
            workload_name=str(raw_anomaly.get("workload_name") or resource_name),
            summary=summary,
            confidence=confidence,
            evidence=evidence,
        )

        pod = pods_by_name.get(resource_name)
        if pod is not None:
            self._enrich_anomaly_with_pod_owner(anomaly, pod)
            self._enrich_anomaly_with_container_details(anomaly, pod)
        self._enrich_anomaly_with_workload_resources(anomaly, deployments_by_name)
        return anomaly

    def _default_resource_kind_for_anomaly(self, anomaly_type: str) -> str:
        if anomaly_type == "NodeNotReady":
            return "Node"
        if anomaly_type == "DeploymentStalled":
            return "Deployment"
        return "Pod"

    def _default_severity_for_anomaly(self, anomaly_type: str) -> str:
        if anomaly_type == "NodeNotReady":
            return "critical"
        if anomaly_type in {"OOMKilled", "CrashLoopBackOff", "DeploymentStalled"}:
            return "high"
        return "medium"

    def _normalize_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.6
        return max(0.0, min(1.0, confidence))

    def _normalize_evidence(self, value: Any, *, summary: str) -> list[str]:
        if isinstance(value, list):
            evidence = [str(item).strip() for item in value if str(item).strip()]
            return evidence or [summary]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return [summary]

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
                evidence=self._image_pull_event_evidence(reason=reason, message=message),
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
                evidence=self._evicted_event_evidence(reason=reason, message=message),
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
            evidence = [
                f"pod phase: {phase}",
                "waiting reason: ImagePullBackOff",
            ]
            evidence.extend(self._image_pull_pod_evidence(pod))
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
                evidence=evidence,
            )

        if str(pod.get("reason") or "") == "Evicted":
            evidence = [
                "pod status reason: Evicted",
                f"pod phase: {phase}",
            ]
            evidence.extend(self._evicted_pod_evidence(pod))
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
                evidence=evidence,
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

    def _enrich_anomaly_with_container_details(self, anomaly: Anomaly, pod: dict[str, Any]) -> None:
        statuses = pod.get("container_statuses") or []
        if not statuses:
            return
        metrics = dict(anomaly.get("metrics") or {})
        if metrics.get("container_name"):
            anomaly["metrics"] = metrics
            return
        first_status = statuses[0]
        if isinstance(first_status, dict) and first_status.get("name"):
            metrics["container_name"] = first_status["name"]
        anomaly["metrics"] = metrics

    def _enrich_anomaly_with_workload_resources(
        self,
        anomaly: Anomaly,
        deployments_by_name: dict[str, dict[str, Any]],
    ) -> None:
        workload_kind = str(anomaly.get("workload_kind") or "")
        workload_name = str(anomaly.get("workload_name") or "")
        if workload_kind != "Deployment" or not workload_name:
            return
        deployment = deployments_by_name.get(workload_name)
        if not isinstance(deployment, dict):
            return
        containers = deployment.get("containers") or []
        if not isinstance(containers, list) or not containers:
            return

        metrics = dict(anomaly.get("metrics") or {})
        container_name = str(metrics.get("container_name") or "")
        selected_container = None
        if container_name:
            for container in containers:
                if str(container.get("name") or "") == container_name:
                    selected_container = container
                    break
        if selected_container is None and len(containers) == 1:
            selected_container = containers[0]
        if selected_container is None:
            return

        selected_name = str(selected_container.get("name") or "")
        cpu_limit = ((selected_container.get("resources") or {}).get("limits") or {}).get("cpu")
        memory_limit = ((selected_container.get("resources") or {}).get("limits") or {}).get("memory")
        memory_request = ((selected_container.get("resources") or {}).get("requests") or {}).get("memory")
        if selected_name:
            metrics["container_name"] = selected_name
        if cpu_limit:
            metrics["current_cpu_limit"] = str(cpu_limit)
        if memory_limit:
            metrics["current_memory_limit"] = str(memory_limit)
        if memory_request:
            metrics["current_memory_request"] = str(memory_request)
        anomaly["metrics"] = metrics

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
            self._enrich_anomaly_with_container_details(anomaly, pod)
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
        current_limit = ((anomaly.get("metrics") or {}).get("current_cpu_limit") if isinstance(anomaly.get("metrics"), dict) else None)
        if isinstance(ratio, (float, int)):
            if current_limit:
                return (
                    f"Increase the CPU limit for {workload} from {current_limit} by roughly 50% and verify "
                    f"the throttling ratio drops below the threshold; Prometheus reports {float(ratio):.2f}."
                )
            return f"Increase the CPU limit for {workload} by roughly 50% and verify the throttling ratio drops below the threshold; Prometheus reports {float(ratio):.2f}."
        return f"Review CPU requests and limits for {workload}; Prometheus indicates sustained CPU throttling."

    def _cpu_throttling_patch(self, anomaly: Anomaly) -> dict[str, Any] | None:
        if not self.allow_workload_patches:
            return None
        workload_kind = str(anomaly.get("workload_kind") or "Pod")
        if workload_kind != "Deployment":
            return None
        metrics = anomaly.get("metrics") if isinstance(anomaly.get("metrics"), dict) else {}
        container_name = str(metrics.get("container_name") or "")
        current_limit = str(metrics.get("current_cpu_limit") or "")
        suggested_limit = self._scale_cpu_limit(current_limit, factor=1.5)
        if not container_name or not suggested_limit:
            return None
        return {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": container_name,
                                "resources": {
                                    "limits": {"cpu": suggested_limit},
                                },
                            }
                        ]
                    }
                }
            }
        }

    def _scale_cpu_limit(self, value: str, *, factor: float) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        if raw.endswith("m"):
            number = raw[:-1]
            try:
                millicores = float(number)
            except ValueError:
                return None
            scaled = max(int(round(millicores * factor)), int(millicores) + 1)
            return f"{scaled}m"
        try:
            cores = float(raw)
        except ValueError:
            return None
        scaled = max(round(cores * factor, 3), cores)
        return f"{scaled:g}"

    def _image_pull_recommendation(self, anomaly: Anomaly) -> str:
        workload = self._workload_label(anomaly)
        evidence_text = " ".join(str(item) for item in anomaly.get("evidence", []))
        image = self._extract_image_reference(evidence_text)
        if image:
            return (
                f"Inspect the failing image `{image}`, registry credentials, and pull policy for {workload}, "
                "then alert a human operator with the exact image pull failure."
            )
        return f"Inspect the image reference, registry credentials, and pull policy for {workload}, then alert a human operator with the failing image details."

    def _image_pull_event_evidence(self, *, reason: str, message: str) -> list[str]:
        evidence = [reason or "ImagePullBackOff"]
        if message:
            evidence.append(message)
        image = self._extract_image_reference(message)
        if image:
            evidence.append(f"image reference: {image}")
        return evidence

    def _image_pull_pod_evidence(self, pod: dict[str, Any]) -> list[str]:
        evidence: list[str] = []
        for status in pod.get("container_statuses", []):
            if not isinstance(status, dict):
                continue
            waiting_reason = str(status.get("waiting_reason") or "")
            if waiting_reason != "ImagePullBackOff":
                continue
            container_name = str(status.get("name") or "unknown")
            waiting_message = str(status.get("waiting_message") or "")
            image = str(status.get("image") or "")
            pull_policy = str(status.get("image_pull_policy") or "")
            evidence.append(f"container: {container_name}")
            if image:
                evidence.append(f"image reference: {image}")
            if pull_policy:
                evidence.append(f"image pull policy: {pull_policy}")
            if waiting_message:
                evidence.append(f"image pull error: {waiting_message}")
            break
        return evidence

    def _evicted_event_evidence(self, *, reason: str, message: str) -> list[str]:
        evidence = [reason or "Evicted"]
        if message:
            evidence.append(message)
        pressure = self._extract_node_pressure(message)
        if pressure:
            evidence.append(f"node pressure: {pressure}")
        return evidence

    def _evicted_pod_evidence(self, pod: dict[str, Any]) -> list[str]:
        evidence: list[str] = []
        node_name = str(pod.get("node_name") or "")
        if node_name:
            evidence.append(f"node: {node_name}")
        message = str(pod.get("message") or "")
        if message:
            evidence.append(f"eviction message: {message}")
        pressure = self._extract_node_pressure(message)
        if pressure:
            evidence.append(f"node pressure: {pressure}")
        return evidence

    def _extract_image_reference(self, text: str) -> str | None:
        marker = 'image "'
        lower = text.lower()
        start = lower.find(marker)
        if start == -1:
            return None
        start += len(marker)
        end = text.find('"', start)
        if end == -1:
            return None
        image = text[start:end].strip()
        return image or None

    def _extract_node_pressure(self, text: str) -> str | None:
        lower = text.lower()
        if "memorypressure" in lower or "memory pressure" in lower:
            return "MemoryPressure"
        if "diskpressure" in lower or "disk pressure" in lower:
            return "DiskPressure"
        if "pidpressure" in lower or "pid pressure" in lower:
            return "PIDPressure"
        if "ephemeral-storage" in lower:
            return "EphemeralStoragePressure"
        return None

    def _oomkill_recommendation(self, anomaly: Anomaly) -> str:
        workload = self._workload_label(anomaly)
        current_limit = self._oomkill_memory_value(anomaly, "current_memory_limit")
        suggested_limit = self._oomkill_scaled_memory_value(anomaly, "current_memory_limit")
        if current_limit and suggested_limit:
            return (
                f"Increase the memory limit for {workload} from {current_limit} to about {suggested_limit} "
                "and then restart the affected pod or rollout."
            )
        return f"Increase the memory limit for {workload} by roughly 50% and then restart the affected pod or rollout."

    def _oomkill_patch(self, anomaly: Anomaly) -> dict[str, Any] | None:
        if not self.allow_workload_patches:
            return None
        workload_kind = str(anomaly.get("workload_kind") or "Pod")
        if workload_kind != "Deployment":
            return None
        metrics = anomaly.get("metrics") if isinstance(anomaly.get("metrics"), dict) else {}
        container_name = str(metrics.get("container_name") or "")
        current_limit = str(metrics.get("current_memory_limit") or "")
        current_request = str(metrics.get("current_memory_request") or "")
        scaled_limit = self._scale_memory_value(current_limit, factor=1.5)
        scaled_request = self._scale_memory_value(current_request, factor=1.5)

        if container_name and (scaled_limit or scaled_request):
            resources: dict[str, Any] = {}
            if scaled_limit:
                resources["limits"] = {"memory": scaled_limit}
            if scaled_request:
                resources["requests"] = {"memory": scaled_request}
            return {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": container_name,
                                    "resources": resources,
                                }
                            ]
                        }
                    }
                }
            }
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

    def _scale_memory_value(self, value: str, *, factor: float) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([A-Za-z]+)?", raw)
        if match is None:
            return None

        number = match.group(1)
        suffix = match.group(2) or ""
        try:
            amount = float(number)
        except ValueError:
            return None
        scaled = max(amount * factor, amount)
        if float(scaled).is_integer():
            return f"{int(scaled)}{suffix}"
        return f"{scaled:g}{suffix}"

    def _oomkill_memory_value(self, anomaly: Anomaly, key: str) -> str | None:
        metrics = anomaly.get("metrics") if isinstance(anomaly.get("metrics"), dict) else {}
        value = str(metrics.get(key) or "").strip()
        return value or None

    def _oomkill_scaled_memory_value(self, anomaly: Anomaly, key: str) -> str | None:
        current_value = self._oomkill_memory_value(anomaly, key)
        return self._scale_memory_value(current_value or "", factor=1.5)

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
