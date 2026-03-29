from __future__ import annotations

from typing import Any

import httpx


class PrometheusClient:
    CPU_THROTTLING_THRESHOLD = 0.5

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

    def get_cpu_throttling(self, *, namespace: str) -> dict[str, Any]:
        promql = (
            "sum by (namespace, pod) (rate(container_cpu_cfs_throttled_periods_total"
            f'{{namespace="{namespace}",container!="",pod!=""}}[5m])) '
            "/ clamp_min(sum by (namespace, pod) (rate(container_cpu_cfs_periods_total"
            f'{{namespace="{namespace}",container!="",pod!=""}}[5m])), 1)'
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
