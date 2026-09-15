import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


class TestHealth:
    async def test_reports_the_service_as_ok(self, client: AsyncClient) -> None:
        response = await client.get("/health")

        assert (response.status_code, response.json()) == (200, {"status": "ok"})
