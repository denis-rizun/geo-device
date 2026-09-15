import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

import structlog

from app.pipeline.constants import (
    FLAPPING_RESTARTS,
    FLAPPING_WINDOW_S,
    SUPERVISOR_CHECK_INTERVAL_S,
    SUPERVISOR_RESTART_DELAY_S,
    TASK_STALL_TIMEOUT_S,
)

logger = structlog.getLogger(__name__)

TaskFactory = Callable[[], Coroutine[Any, Any, None]]
Heartbeat = Callable[[], float]


@dataclass
class TaskSpec:
    name: str
    factory: TaskFactory
    heartbeat: Heartbeat | None = None
    restarts: list[float] = field(default_factory=list, init=False)

    def note_restart(self) -> None:
        self.restarts = [*self._recent(), monotonic()]

    @property
    def flapping(self) -> bool:
        return len(self._recent()) >= FLAPPING_RESTARTS

    def _recent(self) -> list[float]:
        now = monotonic()
        return [at for at in self.restarts if now - at < FLAPPING_WINDOW_S]


class Supervisor:
    def __init__(self) -> None:
        self._specs: list[TaskSpec] = []
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._monitor: asyncio.Task[None] | None = None

    def add(self, name: str, factory: TaskFactory, heartbeat: Heartbeat | None = None) -> None:
        self._specs.append(TaskSpec(name=name, factory=factory, heartbeat=heartbeat))

    @property
    def healthy(self) -> bool:
        return all(self._is_running(spec) and not spec.flapping for spec in self._specs)

    @property
    def status(self) -> dict[str, Any]:
        return {
            "running": sum(1 for spec in self._specs if self._is_running(spec)),
            "tasks": len(self._specs),
            "restarted": sorted(spec.name for spec in self._specs if spec.restarts),
        }

    async def start(self) -> None:
        for spec in self._specs:
            self._spawn(spec)

        self._monitor = asyncio.create_task(self._monitor_loop(), name="supervisor")
        logger.info("supervisor started", tasks=[spec.name for spec in self._specs])

    async def stop(self) -> None:
        if self._monitor:
            self._monitor.cancel()
            await asyncio.gather(self._monitor, return_exceptions=True)
            self._monitor = None

        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("supervisor stopped")

    def _is_running(self, spec: TaskSpec) -> bool:
        task = self._tasks.get(spec.name)
        return task is not None and not task.done()

    def _spawn(self, spec: TaskSpec) -> None:
        self._tasks[spec.name] = asyncio.create_task(spec.factory(), name=spec.name)

    async def _monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(SUPERVISOR_CHECK_INTERVAL_S)
            for spec in self._specs:
                await self._check(spec)

    async def _check(self, spec: TaskSpec) -> None:
        task = self._tasks.get(spec.name)
        if not task:
            await self._restart(spec, reason="missing")
            return

        if task.done():
            await self._restart(spec, reason="exited", error=None if task.cancelled() else task.exception())
            return

        if spec.heartbeat and monotonic() - spec.heartbeat() > TASK_STALL_TIMEOUT_S:
            await self._restart(spec, reason="stalled")

    async def _restart(self, spec: TaskSpec, reason: str, error: BaseException | None = None) -> None:
        task = self._tasks.pop(spec.name, None)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        spec.note_restart()
        logger.error(
            "supervised task restarting",
            task=spec.name,
            reason=reason,
            error=str(error) if error else None,
        )
        await asyncio.sleep(SUPERVISOR_RESTART_DELAY_S)
        self._spawn(spec)
