from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class AuditLogger:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def log(self, entry: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(dict(entry), sort_keys=True))
            file_handle.write("\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as file_handle:
            for line in file_handle:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
        return records

    def read_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        records = self.read_all()
        if limit <= 0:
            return []
        return records[-limit:]

    def read_incident(self, incident_id: str) -> list[dict[str, Any]]:
        return [record for record in self.read_all() if record.get("incident_id") == incident_id]

    def summarize_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for record in self.read_recent(limit=limit):
            summaries.append(
                {
                    "incident_id": record.get("incident_id"),
                    "timestamp": record.get("timestamp"),
                    "anomaly_type": record.get("anomaly_type"),
                    "decision": record.get("decision"),
                    "action": record.get("action"),
                    "result": record.get("result"),
                }
            )
        return summaries

    def query(
        self,
        *,
        limit: int = 20,
        incident_id: str | None = None,
        anomaly_type: str | None = None,
        decision: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        records = self.read_all()
        if incident_id:
            records = [record for record in records if record.get("incident_id") == incident_id]
        if anomaly_type:
            records = [record for record in records if record.get("anomaly_type") == anomaly_type]
        if decision:
            records = [record for record in records if record.get("decision") == decision]
        if search:
            needle = search.lower()
            records = [
                record
                for record in records
                if needle in json.dumps(record, sort_keys=True).lower()
            ]
        if limit <= 0:
            return []
        return records[-limit:]
