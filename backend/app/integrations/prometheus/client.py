from __future__ import annotations

import time
from typing import Any

import httpx


class PrometheusClient:
    CPU_THROTTLING_THRESHOLD = 0.5
    CPU_THROTTLING_LOOKBACK = "5m"
    CPU_THROTTLING_VERIFY_LOOKBACK = "1m"

    def __init__(self, *, base_url: str | None) -> None:
        self.base_url = (base_url or "").rstrip("/")

    def is_configured(self) -> bool:
        return bool(self.base_url)

    def query(self, promql: str) -> dict[str, Any]:
        if not self.is_configured():
            return {"status": "error", "error": "Prometheus is not configured.", "data": {"result": []}}

        try:
            response = httpx.get(
                f"{self.base_url}/api/v1/query",
                params={"query": promql},
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                return {"status": "error", "error": "Unexpected Prometheus response.", "data": {"result": []}}
            return payload
        except Exception as exc:
            return {"status": "error", "error": str(exc), "data": {"result": []}}

    def get_cpu_throttling(self, *, namespace: str, lookback: str = CPU_THROTTLING_LOOKBACK) -> dict[str, Any]:
        promql = (
            "sum by (namespace, pod) (rate(container_cpu_cfs_throttled_periods_total"
            f'{{namespace="{namespace}",container!="",pod!=""}}[{lookback}])) '
            "/ clamp_min(sum by (namespace, pod) (rate(container_cpu_cfs_periods_total"
            f'{{namespace="{namespace}",container!="",pod!=""}}[{lookback}])), 1)'
        )
        payload = self.query(promql)
        result = ((payload.get("data") or {}).get("result") if isinstance(payload, dict) else None) or []
        metrics: list[dict[str, Any]] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            metric = item.get("metric") or {}
            value = item.get("value") or []
            if len(value) < 2:
                continue
            try:
                ratio = float(value[1])
            except (TypeError, ValueError):
                continue
            pod_name = str(metric.get("pod") or "")
            if not pod_name:
                continue
            metrics.append(
                {
                    "namespace": str(metric.get("namespace") or namespace),
                    "pod": pod_name,
                    "ratio": ratio,
                    "threshold": self.CPU_THROTTLING_THRESHOLD,
                }
            )

        return {
            "status": payload.get("status", "error") if isinstance(payload, dict) else "error",
            "error": payload.get("error") if isinstance(payload, dict) else None,
            "metrics": metrics,
        }

    def verify_cpu_throttling_recovery(
        self,
        *,
        namespace: str,
        pod_names: list[str],
        threshold: float | None = None,
        timeout_seconds: int = 60,
        poll_interval_seconds: float = 5.0,
    ) -> dict[str, Any]:
        expected_pods = {str(name) for name in pod_names if name}
        if not expected_pods:
            return {
                "ok": False,
                "recovered": False,
                "message": "No workload pods were available to verify CPU throttling recovery.",
                "metrics": [],
            }

        threshold_value = self.CPU_THROTTLING_THRESHOLD if threshold is None else float(threshold)
        deadline = time.time() + timeout_seconds
        last_metrics: list[dict[str, Any]] = []
        last_error: str | None = None

        while time.time() < deadline:
            payload = self.get_cpu_throttling(namespace=namespace, lookback=self.CPU_THROTTLING_VERIFY_LOOKBACK)
            metrics = payload.get("metrics") if isinstance(payload, dict) else None
            last_error = payload.get("error") if isinstance(payload, dict) else None
            relevant_metrics = [
                metric
                for metric in (metrics or [])
                if str(metric.get("pod") or "") in expected_pods
            ]
            last_metrics = relevant_metrics

            if payload.get("status") == "error" and not relevant_metrics:
                return {
                    "ok": False,
                    "recovered": False,
                    "message": last_error or "Prometheus CPU throttling query failed.",
                    "metrics": [],
                }

            observed_pods = {str(metric.get("pod") or "") for metric in relevant_metrics}
            if observed_pods == expected_pods and relevant_metrics:
                try:
                    all_healthy = all(float(metric.get("ratio") or 0.0) <= threshold_value for metric in relevant_metrics)
                except (TypeError, ValueError):
                    all_healthy = False
                if all_healthy:
                    pod_list = ", ".join(sorted(expected_pods))
                    return {
                        "ok": True,
                        "recovered": True,
                        "message": (
                            f"CPU throttling ratios dropped below {threshold_value:.2f} for pods {pod_list}."
                        ),
                        "metrics": relevant_metrics,
                    }

            time.sleep(poll_interval_seconds)

        if last_metrics:
            offenders = []
            for metric in last_metrics:
                try:
                    ratio = float(metric.get("ratio") or 0.0)
                except (TypeError, ValueError):
                    continue
                if ratio > threshold_value:
                    offenders.append(f"{metric.get('pod')}={ratio:.2f}")
            if offenders:
                message = (
                    "CPU throttling remained above threshold after rollout for "
                    + ", ".join(offenders)
                    + "."
                )
            else:
                missing = sorted(expected_pods - {str(metric.get("pod") or "") for metric in last_metrics})
                message = (
                    "Timed out waiting for Prometheus throttling metrics for pods "
                    + ", ".join(missing)
                    + "."
                )
        else:
            pod_list = ", ".join(sorted(expected_pods))
            message = last_error or f"Timed out waiting for CPU throttling recovery metrics for pods {pod_list}."

        return {
            "ok": False,
            "recovered": False,
            "message": message,
            "metrics": last_metrics,
        }
