import asyncio
from collections.abc import AsyncGenerator
from time import monotonic

import pytest

from app.pipeline.constants import (
    FLAPPING_RESTARTS,
    FLAPPING_WINDOW_S,
    SUPERVISOR_CHECK_INTERVAL_S,
    SUPERVISOR_RESTART_DELAY_S,
)
from app.pipeline.worker.lifecycle import Supervisor, TaskSpec

pytestmark = pytest.mark.unit

RESTART_TIMEOUT_S = SUPERVISOR_CHECK_INTERVAL_S + SUPERVISOR_RESTART_DELAY_S + 5.0


async def forever() -> None:
    await asyncio.Event().wait()


class TestTaskSpec:
    def test_starts_without_restarts(self) -> None:
        spec = TaskSpec(name="worker", factory=forever)

        assert spec.restarts == []

    def test_is_not_flapping_below_the_threshold(self) -> None:
        spec = TaskSpec(name="worker", factory=forever)

        for _ in range(FLAPPING_RESTARTS - 1):
            spec.note_restart()

        assert spec.flapping is False

    def test_is_flapping_once_the_threshold_is_reached(self) -> None:
        spec = TaskSpec(name="worker", factory=forever)

        for _ in range(FLAPPING_RESTARTS):
            spec.note_restart()

        assert spec.flapping is True

    def test_forgets_restarts_older_than_the_window(self) -> None:
        spec = TaskSpec(name="worker", factory=forever)
        spec.restarts = [monotonic() - FLAPPING_WINDOW_S - 1.0] * FLAPPING_RESTARTS

        spec.note_restart()

        assert spec.restarts == pytest.approx([spec.restarts[-1]])


class TestSupervisor:
    @pytest.fixture
    async def supervisor(self) -> AsyncGenerator[Supervisor]:
        supervisor = Supervisor()
        yield supervisor
        await supervisor.stop()

    async def test_reports_healthy_with_no_tasks(self, supervisor: Supervisor) -> None:
        await supervisor.start()

        assert supervisor.healthy is True

    async def test_reports_running_tasks(self, supervisor: Supervisor) -> None:
        supervisor.add("worker-0", forever)
        supervisor.add("worker-1", forever)
        await supervisor.start()

        assert supervisor.status == {"running": 2, "tasks": 2, "restarted": []}

    async def test_is_healthy_while_every_task_runs(self, supervisor: Supervisor) -> None:
        supervisor.add("worker-0", forever)
        await supervisor.start()

        assert supervisor.healthy is True

    async def test_stop_cancels_every_task(self, supervisor: Supervisor) -> None:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def task() -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        supervisor.add("worker-0", task)
        await supervisor.start()
        await started.wait()
        await supervisor.stop()

        assert cancelled.is_set() is True

    async def test_restarts_a_task_that_exited(self, supervisor: Supervisor) -> None:
        starts = 0
        restarted = asyncio.Event()

        async def flaky() -> None:
            nonlocal starts
            starts += 1
            if starts > 1:
                restarted.set()
                await asyncio.Event().wait()

        supervisor.add("worker-0", flaky)
        await supervisor.start()

        async with asyncio.timeout(RESTART_TIMEOUT_S):
            await restarted.wait()

        assert supervisor.status["restarted"] == ["worker-0"]
