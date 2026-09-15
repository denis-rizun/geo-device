import pytest

from app.pipeline.utils import Backoff, Ticker

pytestmark = pytest.mark.unit


class TestBackoff:
    @pytest.fixture
    def backoff(self) -> Backoff:
        return Backoff(start=0.001, limit=0.004)

    async def test_first_sleep_uses_the_start_delay(self, backoff: Backoff) -> None:
        assert await backoff.sleep() == 0.001

    async def test_delay_doubles_on_every_sleep(self, backoff: Backoff) -> None:
        delays = [await backoff.sleep() for _ in range(3)]

        assert delays == [0.001, 0.002, 0.004]

    async def test_delay_never_exceeds_the_limit(self, backoff: Backoff) -> None:
        delays = [await backoff.sleep() for _ in range(6)]

        assert delays[-1] == 0.004

    async def test_reset_returns_to_the_start_delay(self, backoff: Backoff) -> None:
        await backoff.sleep()
        await backoff.sleep()
        backoff.reset()

        assert await backoff.sleep() == 0.001


class TestTicker:
    def test_is_not_due_before_the_interval_elapses(self) -> None:
        ticker = Ticker(interval=60.0, jitter=0.0)

        assert ticker.due() is False

    def test_is_due_once_the_interval_has_elapsed(self) -> None:
        ticker = Ticker(interval=0.0, jitter=0.0)

        assert ticker.due() is True

    def test_rearms_itself_after_firing(self) -> None:
        ticker = Ticker(interval=0.0, jitter=0.0)
        ticker.due()

        assert ticker.due() is True
