from __future__ import annotations

import asyncio
from contextlib import suppress

from .graph import AgentRuntime


class BackgroundPoller:
    def __init__(self, *, runtime: AgentRuntime, poll_interval_seconds: int) -> None:
        self.runtime = runtime
        self.poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._last_error: str | None = None
        self._loop_count = 0

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def get_status(self) -> dict[str, object]:
        return {
            "enabled": True,
            "running": self.is_running,
            "poll_interval_seconds": self.poll_interval_seconds,
            "loop_count": self._loop_count,
            "last_error": self._last_error,
        }

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="k8s-whisperer-poller")

    async def stop(self) -> None:
        self._running = False
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def trigger_once(self) -> dict[str, object]:
        return await asyncio.to_thread(self.runtime.run_once, deduplicate=True)

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await asyncio.to_thread(self.runtime.run_once, deduplicate=True)
                self._loop_count += 1
                self._last_error = None
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                self._last_error = str(exc)
            await asyncio.sleep(self.poll_interval_seconds)
