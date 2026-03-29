from __future__ import annotations

import pickle
from collections import defaultdict
from pathlib import Path
from threading import RLock
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver


class PersistentInMemorySaver(InMemorySaver):
    """Disk-backed wrapper around LangGraph's in-memory saver.

    This keeps full compatibility with the built-in saver while persisting the
    internal checkpoint state after every mutation so HITL resume survives a
    process restart in the demo environment.
    """

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = RLock()
        super().__init__()
        self._load_from_disk()

    def put(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        with self._lock:
            result = super().put(config, checkpoint, metadata, new_versions)
            self._persist_to_disk()
            return result

    def put_writes(self, config: Any, writes: Any, task_id: str, task_path: str = "") -> None:
        with self._lock:
            super().put_writes(config, writes, task_id, task_path)
            self._persist_to_disk()

    def delete_thread(self, thread_id: str) -> None:
        with self._lock:
            super().delete_thread(thread_id)
            self._persist_to_disk()

    def list_threads(self) -> list[str]:
        with self._lock:
            return sorted(self.storage.keys())

    def reset(self) -> None:
        with self._lock:
            self.storage.clear()
            self.writes.clear()
            self.blobs.clear()
            if self.path.exists():
                self.path.unlink()

    def _load_from_disk(self) -> None:
        if not self.path.exists():
            return

        with self.path.open("rb") as file_handle:
            payload = pickle.load(file_handle)

        storage = defaultdict(lambda: defaultdict(dict))
        for thread_id, namespace_map in payload.get("storage", {}).items():
            storage[thread_id] = defaultdict(dict)
            for checkpoint_ns, checkpoint_map in namespace_map.items():
                storage[thread_id][checkpoint_ns] = dict(checkpoint_map)

        self.storage = storage
        self.writes = defaultdict(dict, payload.get("writes", {}))
        self.blobs = dict(payload.get("blobs", {}))

    def _persist_to_disk(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "storage": {
                thread_id: {checkpoint_ns: dict(checkpoints) for checkpoint_ns, checkpoints in namespace_map.items()}
                for thread_id, namespace_map in self.storage.items()
            },
            "writes": dict(self.writes),
            "blobs": dict(self.blobs),
        }
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with temp_path.open("wb") as file_handle:
            pickle.dump(payload, file_handle)
        temp_path.replace(self.path)
