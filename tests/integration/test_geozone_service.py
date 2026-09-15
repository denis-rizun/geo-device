import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.domains.geozones.schemas import GeozoneCreateRequest, GeozoneUpdateRequest
from app.domains.geozones.service import GeozoneService

pytestmark = pytest.mark.integration

USER = "user-1"
OTHER_USER = "user-2"


def make_payload(
    name: str = "home", lat: float = 50.45, lon: float = 30.52, radius_m: float = 500.0
) -> GeozoneCreateRequest:
    return GeozoneCreateRequest(name=name, lat=lat, lon=lon, radius_m=radius_m)


class TestCreate:
    @pytest.fixture
    def service(self, db_session: AsyncSession) -> GeozoneService:
        return GeozoneService(db_session)

    async def test_returns_the_stored_geozone(self, service: GeozoneService) -> None:
        created = await service.create(USER, make_payload())

        assert (created.user_id, created.name, created.radius_m) == (USER, "home", 500.0)

    async def test_round_trips_the_centre_coordinates(self, service: GeozoneService) -> None:
        created = await service.create(USER, make_payload(lat=50.45, lon=30.52))

        assert (created.lat, created.lon) == pytest.approx((50.45, 30.52))

    async def test_rejects_a_duplicate_name_for_the_same_user(self, service: GeozoneService) -> None:
        await service.create(USER, make_payload())

        with pytest.raises(ConflictError):
            await service.create(USER, make_payload())

    async def test_allows_the_same_name_for_another_user(self, service: GeozoneService) -> None:
        await service.create(USER, make_payload())

        created = await service.create(OTHER_USER, make_payload())

        assert created.user_id == OTHER_USER


class TestRetrieve:
    @pytest.fixture
    def service(self, db_session: AsyncSession) -> GeozoneService:
        return GeozoneService(db_session)

    async def test_returns_an_own_geozone(self, service: GeozoneService) -> None:
        created = await service.create(USER, make_payload())

        assert await service.retrieve(created.id, USER) == created

    async def test_hides_a_geozone_owned_by_another_user(self, service: GeozoneService) -> None:
        created = await service.create(USER, make_payload())

        with pytest.raises(NotFoundError):
            await service.retrieve(created.id, OTHER_USER)

    async def test_rejects_an_unknown_id(self, service: GeozoneService) -> None:
        with pytest.raises(NotFoundError):
            await service.retrieve(999_999, USER)


class TestList:
    @pytest.fixture
    def service(self, db_session: AsyncSession) -> GeozoneService:
        return GeozoneService(db_session)

    async def test_returns_newest_first(self, service: GeozoneService) -> None:
        first = await service.create(USER, make_payload(name="first"))
        second = await service.create(USER, make_payload(name="second"))

        assert [zone.id for zone in await service.list(USER)] == [second.id, first.id]

    async def test_returns_only_own_geozones(self, service: GeozoneService) -> None:
        await service.create(USER, make_payload())
        await service.create(OTHER_USER, make_payload())

        assert [zone.user_id for zone in await service.list(USER)] == [USER]

    async def test_applies_limit_and_offset(self, service: GeozoneService) -> None:
        first = await service.create(USER, make_payload(name="first"))
        await service.create(USER, make_payload(name="second"))

        assert [zone.id for zone in await service.list(USER, limit=1, offset=1)] == [first.id]

    async def test_returns_nothing_for_a_user_without_geozones(self, service: GeozoneService) -> None:
        assert await service.list(USER) == []


class TestUpdate:
    @pytest.fixture
    def service(self, db_session: AsyncSession) -> GeozoneService:
        return GeozoneService(db_session)

    async def test_renames_a_geozone(self, service: GeozoneService) -> None:
        created = await service.create(USER, make_payload())

        updated = await service.update(created, GeozoneUpdateRequest(name="office"))

        assert updated.name == "office"

    async def test_moves_the_centre(self, service: GeozoneService) -> None:
        created = await service.create(USER, make_payload())

        updated = await service.update(created, GeozoneUpdateRequest(lat=10.0, lon=20.0))

        assert (updated.lat, updated.lon) == pytest.approx((10.0, 20.0))

    async def test_leaves_untouched_fields_alone(self, service: GeozoneService) -> None:
        created = await service.create(USER, make_payload())

        updated = await service.update(created, GeozoneUpdateRequest(radius_m=900.0))

        assert (updated.name, updated.radius_m) == ("home", 900.0)

    async def test_rejects_a_name_taken_by_another_geozone(self, service: GeozoneService) -> None:
        await service.create(USER, make_payload(name="office"))
        created = await service.create(USER, make_payload(name="home"))

        with pytest.raises(ConflictError):
            await service.update(created, GeozoneUpdateRequest(name="office"))

    async def test_rejects_a_geozone_owned_by_another_user(self, service: GeozoneService) -> None:
        created = await service.create(USER, make_payload())
        foreign = created.model_copy(update={"user_id": OTHER_USER})

        with pytest.raises(NotFoundError):
            await service.update(foreign, GeozoneUpdateRequest(name="office"))


class TestDelete:
    @pytest.fixture
    def service(self, db_session: AsyncSession) -> GeozoneService:
        return GeozoneService(db_session)

    async def test_removes_the_geozone(self, service: GeozoneService) -> None:
        created = await service.create(USER, make_payload())

        await service.delete(created)

        with pytest.raises(NotFoundError):
            await service.retrieve(created.id, USER)

    async def test_rejects_a_geozone_owned_by_another_user(self, service: GeozoneService) -> None:
        created = await service.create(USER, make_payload())
        foreign = created.model_copy(update={"user_id": OTHER_USER})

        with pytest.raises(NotFoundError):
            await service.delete(foreign)

    async def test_rejects_a_second_delete(self, service: GeozoneService) -> None:
        created = await service.create(USER, make_payload())
        await service.delete(created)

        with pytest.raises(NotFoundError):
            await service.delete(created)
