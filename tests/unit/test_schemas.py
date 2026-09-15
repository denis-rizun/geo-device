from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from app.domains.devices.schemas import LocationBatchRequest, LocationRequest
from app.domains.geozones.schemas import GeozoneCreateRequest, GeozoneUpdateRequest

pytestmark = pytest.mark.unit


class TestLocationRequest:
    def test_naive_recorded_at_is_treated_as_utc(self) -> None:
        request = LocationRequest(device_id="dev-1", lat=1.0, lon=2.0, recorded_at=datetime(2026, 9, 15, 10, 0))

        assert request.recorded_at == datetime(2026, 9, 15, 10, 0, tzinfo=UTC)

    def test_aware_recorded_at_keeps_its_offset(self) -> None:
        recorded_at = datetime(2026, 9, 15, 10, 0, tzinfo=timezone(timedelta(hours=3)))

        request = LocationRequest(device_id="dev-1", lat=1.0, lon=2.0, recorded_at=recorded_at)

        assert request.recorded_at == recorded_at

    def test_recorded_at_defaults_to_now(self) -> None:
        request = LocationRequest(device_id="dev-1", lat=1.0, lon=2.0)

        assert request.recorded_at.tzinfo is UTC

    @pytest.mark.parametrize(
        ("lat", "lon"),
        [(90.1, 0.0), (-90.1, 0.0), (0.0, 180.1), (0.0, -180.1)],
    )
    def test_rejects_coordinates_outside_the_globe(self, lat: float, lon: float) -> None:
        with pytest.raises(ValidationError):
            LocationRequest(device_id="dev-1", lat=lat, lon=lon)

    @pytest.mark.parametrize("device_id", ["", "d" * 65])
    def test_rejects_device_ids_outside_the_length_limits(self, device_id: str) -> None:
        with pytest.raises(ValidationError):
            LocationRequest(device_id=device_id, lat=1.0, lon=2.0)

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            LocationRequest(device_id="dev-1", lat=1.0, lon=2.0, speed=10)  # type: ignore[call-arg]


class TestLocationBatchRequest:
    def test_rejects_an_empty_batch(self) -> None:
        with pytest.raises(ValidationError):
            LocationBatchRequest(points=[])

    def test_rejects_a_batch_over_the_configured_limit(self) -> None:
        point = {"device_id": "dev-1", "lat": 1.0, "lon": 2.0}

        with pytest.raises(ValidationError):
            LocationBatchRequest(points=[point] * 1_001)


class TestGeozoneCreateRequest:
    @pytest.mark.parametrize("radius_m", [0.0, -1.0, 100_000.1])
    def test_rejects_a_radius_outside_the_allowed_range(self, radius_m: float) -> None:
        with pytest.raises(ValidationError):
            GeozoneCreateRequest(name="home", lat=1.0, lon=2.0, radius_m=radius_m)

    @pytest.mark.parametrize("name", ["", "n" * 129])
    def test_rejects_names_outside_the_length_limits(self, name: str) -> None:
        with pytest.raises(ValidationError):
            GeozoneCreateRequest(name=name, lat=1.0, lon=2.0, radius_m=100.0)


class TestGeozoneUpdateRequest:
    def test_accepts_a_partial_update(self) -> None:
        request = GeozoneUpdateRequest(name="office")

        assert request.model_dump(exclude_unset=True) == {"name": "office"}

    def test_accepts_a_coordinate_pair(self) -> None:
        request = GeozoneUpdateRequest(lat=1.0, lon=2.0)

        assert request.model_dump(exclude_unset=True) == {"lat": 1.0, "lon": 2.0}

    @pytest.mark.parametrize("payload", [{"lat": 1.0}, {"lon": 2.0}])
    def test_rejects_a_half_specified_coordinate(self, payload: dict[str, Any]) -> None:
        with pytest.raises(ValidationError, match="lat and lon must be provided together"):
            GeozoneUpdateRequest(**payload)

    def test_rejects_explicit_nulls(self) -> None:
        with pytest.raises(ValidationError, match="fields must not be null: name"):
            GeozoneUpdateRequest(name=None)

    def test_reports_every_explicit_null(self) -> None:
        with pytest.raises(ValidationError, match="fields must not be null: name, radius_m"):
            GeozoneUpdateRequest(name=None, radius_m=None)

    def test_accepts_an_empty_update(self) -> None:
        assert GeozoneUpdateRequest().model_dump(exclude_unset=True) == {}
