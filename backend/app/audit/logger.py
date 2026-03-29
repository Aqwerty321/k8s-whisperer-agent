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
