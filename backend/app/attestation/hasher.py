from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def canonical_incident_json(record: Mapping[str, Any]) -> str:
    return json.dumps(dict(record), sort_keys=True, separators=(",", ":"))


def hash_incident_record(record: Mapping[str, Any]) -> str:
    payload = canonical_incident_json(record).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
