from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Literal

from ..models import Anomaly


@dataclass
class IncidentRecord:
    incident_id: str
    status: Literal["open", "resolved"]
    updated_at: float


class IncidentTracker:
    def __init__(self, *, dedup_window_seconds: int) -> None:
        self.dedup_window_seconds = dedup_window_seconds
        self._records: dict[str, IncidentRecord] = {}
        self._lock = Lock()

    def filter_anomalies(
        self,
        *,
        incident_id: str,
        anomalies: list[Anomaly],
        deduplicate: bool,
    ) -> tuple[list[Anomaly], list[Anomaly]]:
        if not deduplicate:
            return anomalies, []

        now = time.time()
        filtered: list[Anomaly] = []
        suppressed: list[Anomaly] = []

        with self._lock:
            self._prune_locked(now)
            for anomaly in anomalies:
                signature = self._signature(anomaly)
                record = self._records.get(signature)
                if record is not None:
                    if record.status == "open":
                        record.updated_at = now
                        suppressed.append(anomaly)
                        continue
                    if now - record.updated_at < self.dedup_window_seconds:
                        record.updated_at = now
                        suppressed.append(anomaly)
                        continue

                self._records[signature] = IncidentRecord(
                    incident_id=incident_id,
                    status="open",
                    updated_at=now,
                )
                filtered.append(anomaly)

        return filtered, suppressed

    def hydrate_incident(self, incident: dict[str, object]) -> None:
        anomalies = incident.get("tracker_anomalies")
        if not isinstance(anomalies, list) or not anomalies:
            anomalies = incident.get("anomalies")
        if not isinstance(anomalies, list) or not anomalies:
            return

        incident_id = str(incident.get("incident_id") or "")
        if not incident_id:
            return

        status: Literal["open", "resolved"] = "open" if bool(incident.get("awaiting_human")) else "resolved"
        now = time.time()
        with self._lock:
            self._prune_locked(now)
            for anomaly in anomalies:
                if not isinstance(anomaly, dict):
                    continue
                self._records[self._signature(anomaly)] = IncidentRecord(
                    incident_id=incident_id,
                    status=status,
                    updated_at=now,
                )

    def snapshot(self) -> dict[str, dict[str, object]]:
        now = time.time()
        with self._lock:
            self._prune_locked(now)
            return {
                signature: {
                    "incident_id": record.incident_id,
                    "status": record.status,
                    "updated_at": record.updated_at,
                }
                for signature, record in self._records.items()
            }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()

    def _prune_locked(self, now: float) -> None:
        for signature in list(self._records.keys()):
            record = self._records[signature]
            if record.status == "resolved" and now - record.updated_at >= self.dedup_window_seconds:
                del self._records[signature]

    def _signature(self, anomaly: Anomaly) -> str:
        namespace = str(anomaly.get("namespace") or "default")
        anomaly_type = str(anomaly.get("anomaly_type") or "Unknown")
        resource_kind = str(anomaly.get("resource_kind") or "Pod")
        resource_name = str(anomaly.get("resource_name") or "unknown")
        return f"{namespace}:{anomaly_type}:{resource_kind}:{resource_name}"
