from typing import Any

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

from app.core.config import config
from app.pipeline import stream
from app.pipeline.constants import PENDING_PINGS_KEY

pytestmark = pytest.mark.e2e

POINT = {"device_id": "dev-1", "lat": 50.45, "lon": 30.52, "recorded_at": "2026-09-15T12:00:00+00:00"}


class TestIngestBatch:
    async def test_accepts_a_batch(self, client_with_redis: AsyncClient) -> None:
        response = await client_with_redis.post("/ingest/batch", json={"points": [POINT]})

        assert (response.status_code, response.json()) == (202, {"accepted": 1, "backlog": 0})

    async def test_queues_the_points(self, client_with_redis: AsyncClient, redis: Redis) -> None:
        await client_with_redis.post("/ingest/batch", json={"points": [POINT, POINT]})

        assert await stream.get_backlog(redis) == 2

    async def test_rejects_an_empty_batch(self, client_with_redis: AsyncClient) -> None:
        response = await client_with_redis.post("/ingest/batch", json={"points": []})

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "point",
        [
            {"device_id": "dev-1", "lat": 91.0, "lon": 30.52},
            {"device_id": "", "lat": 50.45, "lon": 30.52},
            {"device_id": "dev-1", "lat": 50.45, "lon": 30.52, "speed": 10},
        ],
    )
    async def test_rejects_an_invalid_point(self, client_with_redis: AsyncClient, point: dict[str, Any]) -> None:
        response = await client_with_redis.post("/ingest/batch", json={"points": [point]})

        assert response.status_code == 422

    async def test_rejects_a_batch_when_the_backlog_is_full(self, client_with_redis: AsyncClient, redis: Redis) -> None:
        await redis.set(PENDING_PINGS_KEY, config.ingest.BACKLOG_LIMIT + 1)

        response = await client_with_redis.post("/ingest/batch", json={"points": [POINT]})

        assert response.status_code == 503

    async def test_tells_the_client_when_to_retry(self, client_with_redis: AsyncClient, redis: Redis) -> None:
        await redis.set(PENDING_PINGS_KEY, config.ingest.BACKLOG_LIMIT + 1)

        response = await client_with_redis.post("/ingest/batch", json={"points": [POINT]})

        assert response.headers["Retry-After"] == "1"
