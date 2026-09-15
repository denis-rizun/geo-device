from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e

USER = "user-1"
OTHER_USER = "user-2"
HEADERS = {"X-User-ID": USER}
OTHER_HEADERS = {"X-User-ID": OTHER_USER}
PAYLOAD = {"name": "home", "lat": 50.45, "lon": 30.52, "radius_m": 500.0}


async def create(
    client: AsyncClient, payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    response = await client.post("/geozones", json=payload or PAYLOAD, headers=headers or HEADERS)
    return response.json()  # type: ignore[no-any-return]


class TestCreateGeozone:
    async def test_returns_the_created_geozone(self, client_with_db: AsyncClient) -> None:
        response = await client_with_db.post("/geozones", json=PAYLOAD, headers=HEADERS)

        assert response.status_code == 201

    async def test_echoes_the_submitted_fields(self, client_with_db: AsyncClient) -> None:
        created = await create(client_with_db)

        assert (created["name"], created["lat"], created["lon"], created["radius_m"]) == pytest.approx(
            ("home", 50.45, 30.52, 500.0)
        )

    async def test_reports_a_duplicate_name_as_a_conflict(self, client_with_db: AsyncClient) -> None:
        await create(client_with_db)

        response = await client_with_db.post("/geozones", json=PAYLOAD, headers=HEADERS)

        assert response.status_code == 409

    @pytest.mark.parametrize(
        "payload",
        [
            {"name": "home", "lat": 91.0, "lon": 30.52, "radius_m": 500.0},
            {"name": "home", "lat": 50.45, "lon": 30.52, "radius_m": 0.0},
            {"name": "", "lat": 50.45, "lon": 30.52, "radius_m": 500.0},
            {"name": "home", "lat": 50.45, "lon": 30.52},
        ],
    )
    async def test_rejects_an_invalid_payload(self, client_with_db: AsyncClient, payload: dict[str, Any]) -> None:
        response = await client_with_db.post("/geozones", json=payload, headers=HEADERS)

        assert response.status_code == 422


class TestListGeozones:
    async def test_returns_only_own_geozones(self, client_with_db: AsyncClient) -> None:
        await create(client_with_db)
        await create(client_with_db, headers=OTHER_HEADERS)

        response = await client_with_db.get("/geozones", headers=HEADERS)

        assert [zone["user_id"] for zone in response.json()] == [USER]

    async def test_paginates_the_result(self, client_with_db: AsyncClient) -> None:
        first = await create(client_with_db, {**PAYLOAD, "name": "first"})
        await create(client_with_db, {**PAYLOAD, "name": "second"})

        response = await client_with_db.get("/geozones", params={"limit": 1, "offset": 1}, headers=HEADERS)

        assert [zone["id"] for zone in response.json()] == [first["id"]]

    async def test_rejects_an_out_of_range_limit(self, client_with_db: AsyncClient) -> None:
        response = await client_with_db.get("/geozones", params={"limit": 501}, headers=HEADERS)

        assert response.status_code == 422


class TestRetrieveGeozone:
    async def test_returns_an_own_geozone(self, client_with_db: AsyncClient) -> None:
        created = await create(client_with_db)

        response = await client_with_db.get(f"/geozones/{created['id']}", headers=HEADERS)

        assert response.json() == created

    async def test_hides_a_geozone_of_another_user(self, client_with_db: AsyncClient) -> None:
        created = await create(client_with_db)

        response = await client_with_db.get(f"/geozones/{created['id']}", headers=OTHER_HEADERS)

        assert response.status_code == 404

    async def test_rejects_a_non_positive_id(self, client_with_db: AsyncClient) -> None:
        response = await client_with_db.get("/geozones/0", headers=HEADERS)

        assert response.status_code == 422


class TestUpdateGeozone:
    async def test_applies_a_partial_update(self, client_with_db: AsyncClient) -> None:
        created = await create(client_with_db)

        response = await client_with_db.patch(
            f"/geozones/{created['id']}", json={"name": "office"}, headers=HEADERS
        )

        assert response.json()["name"] == "office"

    async def test_reports_a_taken_name_as_a_conflict(self, client_with_db: AsyncClient) -> None:
        await create(client_with_db, {**PAYLOAD, "name": "office"})
        created = await create(client_with_db)

        response = await client_with_db.patch(
            f"/geozones/{created['id']}", json={"name": "office"}, headers=HEADERS
        )

        assert response.status_code == 409

    async def test_rejects_a_half_specified_coordinate(self, client_with_db: AsyncClient) -> None:
        created = await create(client_with_db)

        response = await client_with_db.patch(f"/geozones/{created['id']}", json={"lat": 10.0}, headers=HEADERS)

        assert response.status_code == 422

    async def test_rejects_an_unknown_geozone(self, client_with_db: AsyncClient) -> None:
        response = await client_with_db.patch("/geozones/999999", json={"name": "office"}, headers=HEADERS)

        assert response.status_code == 404


class TestDeleteGeozone:
    async def test_removes_the_geozone(self, client_with_db: AsyncClient) -> None:
        created = await create(client_with_db)

        response = await client_with_db.delete(f"/geozones/{created['id']}", headers=HEADERS)

        assert response.status_code == 204

    async def test_makes_the_geozone_unreachable(self, client_with_db: AsyncClient) -> None:
        created = await create(client_with_db)
        await client_with_db.delete(f"/geozones/{created['id']}", headers=HEADERS)

        response = await client_with_db.get(f"/geozones/{created['id']}", headers=HEADERS)

        assert response.status_code == 404

    async def test_rejects_a_geozone_of_another_user(self, client_with_db: AsyncClient) -> None:
        created = await create(client_with_db)

        response = await client_with_db.delete(f"/geozones/{created['id']}", headers=OTHER_HEADERS)

        assert response.status_code == 404
