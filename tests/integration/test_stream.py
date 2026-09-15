from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis

from app.core.config import config
from app.pipeline import stream
from app.pipeline.constants import GROUP, PENDING_PINGS_KEY, STREAM
from app.pipeline.utils import Ping

pytestmark = pytest.mark.integration

RECORDED_AT = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
CONSUMER = "ingest-0"


def make_pings(count: int, device_prefix: str = "dev") -> list[Ping]:
    return [
        Ping(device_id=f"{device_prefix}-{index}", lat=50.45, lon=30.52, recorded_at=RECORDED_AT)
        for index in range(count)
    ]


class TestEnsureGroup:
    async def test_creates_the_consumer_group(self, redis: Redis) -> None:
        await stream.ensure_group(redis)

        assert [group["name"] for group in await redis.xinfo_groups(STREAM)] == [GROUP.encode()]

    async def test_is_idempotent(self, redis: Redis) -> None:
        await stream.ensure_group(redis)
        await stream.ensure_group(redis)

        assert len(await redis.xinfo_groups(STREAM)) == 1


class TestPublish:
    async def test_publishes_nothing_for_an_empty_batch(self, redis: Redis) -> None:
        await stream.publish(redis, [])

        assert await redis.exists(STREAM) == 0

    async def test_counts_every_published_ping_in_the_backlog(self, redis: Redis) -> None:
        await stream.publish(redis, make_pings(3))

        assert await stream.get_backlog(redis) == 3

    async def test_splits_a_batch_into_chunks(self, redis: Redis) -> None:
        await stream.publish(redis, make_pings(config.ingest.CHUNK_SIZE + 1))

        assert await redis.xlen(STREAM) == 2

    async def test_caps_the_stream_length(self, redis: Redis) -> None:
        await stream.publish(redis, make_pings(3))

        info = await redis.xinfo_stream(STREAM)

        assert info["length"] <= config.ingest.STREAM_MAX_LEN


class TestGetBacklog:
    async def test_reports_zero_for_an_untouched_stream(self, redis: Redis) -> None:
        assert await stream.get_backlog(redis) == 0

    async def test_never_reports_a_negative_backlog(self, redis: Redis) -> None:
        await redis.set(PENDING_PINGS_KEY, -5)

        assert await stream.get_backlog(redis) == 0


class TestReadNew:
    @pytest.fixture
    async def group(self, redis: Redis) -> None:
        await stream.ensure_group(redis)

    async def test_returns_nothing_when_the_stream_is_empty(self, redis: Redis, group: None) -> None:
        assert await stream.read_new(redis, CONSUMER) == []

    async def test_returns_the_published_pings(self, redis: Redis, group: None) -> None:
        pings = make_pings(2)
        await stream.publish(redis, pings)

        chunks = await stream.read_new(redis, CONSUMER)

        assert [ping for chunk in chunks for ping in chunk.pings] == pings

    async def test_does_not_redeliver_a_read_chunk(self, redis: Redis, group: None) -> None:
        await stream.publish(redis, make_pings(1))
        await stream.read_new(redis, CONSUMER)

        assert await stream.read_new(redis, CONSUMER) == []


class TestAck:
    @pytest.fixture
    async def group(self, redis: Redis) -> None:
        await stream.ensure_group(redis)

    async def test_acknowledging_nothing_leaves_the_backlog_alone(self, redis: Redis, group: None) -> None:
        await stream.publish(redis, make_pings(2))

        await stream.ack(redis, [])

        assert await stream.get_backlog(redis) == 2

    async def test_decreases_the_backlog_by_the_acknowledged_pings(self, redis: Redis, group: None) -> None:
        await stream.publish(redis, make_pings(2))
        chunks = await stream.read_new(redis, CONSUMER)

        await stream.ack(redis, chunks)

        assert await stream.get_backlog(redis) == 0

    async def test_clears_the_pending_entries(self, redis: Redis, group: None) -> None:
        await stream.publish(redis, make_pings(2))
        chunks = await stream.read_new(redis, CONSUMER)

        await stream.ack(redis, chunks)

        assert await stream.get_entry_backlog(redis) == 0


class TestClaimStale:
    @pytest.fixture
    async def group(self, redis: Redis) -> None:
        await stream.ensure_group(redis)

    async def test_claims_nothing_when_no_entry_is_idle(self, redis: Redis, group: None) -> None:
        await stream.publish(redis, make_pings(1))
        await stream.read_new(redis, CONSUMER)

        assert await stream.claim_stale(redis, "ingest-1") == []


class TestReconcileBacklog:
    @pytest.fixture
    async def group(self, redis: Redis) -> None:
        await stream.ensure_group(redis)

    async def test_resets_a_stale_counter_once_the_stream_is_drained(self, redis: Redis, group: None) -> None:
        await stream.publish(redis, make_pings(1))
        chunks = await stream.read_new(redis, CONSUMER)
        await redis.xack(STREAM, GROUP, *[chunk.entry_id for chunk in chunks])

        await stream.reconcile_backlog(redis)

        assert await stream.get_backlog(redis) == 0

    async def test_keeps_the_counter_while_entries_are_pending(self, redis: Redis, group: None) -> None:
        await stream.publish(redis, make_pings(2))
        await stream.read_new(redis, CONSUMER)

        await stream.reconcile_backlog(redis)

        assert await stream.get_backlog(redis) == 2
