import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


class TestUserHeader:
    async def test_rejects_a_request_without_the_header(self, client: AsyncClient) -> None:
        response = await client.get("/geozones")

        assert (response.status_code, response.json()) == (401, {"detail": "X-User-ID header is required"})

    async def test_rejects_a_blank_header(self, client: AsyncClient) -> None:
        response = await client.get("/geozones", headers={"X-User-ID": "   "})

        assert response.status_code == 401

    async def test_rejects_an_overlong_header(self, client: AsyncClient) -> None:
        response = await client.get("/geozones", headers={"X-User-ID": "u" * 65})

        assert (response.status_code, response.json()) == (
            401,
            {"detail": "X-User-ID doesn't follow supported format"},
        )
