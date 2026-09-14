from datetime import datetime
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.utils import BaseSchema, Latitude, Longitude, UserId
from app.domains.geozones.constants import MAX_NAME_LENGTH, MAX_RADIUS_M

Name = Annotated[str, Field(min_length=1, max_length=MAX_NAME_LENGTH)]
RadiusM = Annotated[float, Field(gt=0.0, le=MAX_RADIUS_M)]


class GeozoneCreateRequest(BaseSchema):
    name: Name
    lat: Latitude
    lon: Longitude
    radius_m: RadiusM


class GeozoneUpdateRequest(BaseSchema):
    name: Name | None = None
    lat: Latitude | None = None
    lon: Longitude | None = None
    radius_m: RadiusM | None = None

    @model_validator(mode="after")
    def check_center_pair(self) -> Self:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be provided together")
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class GeozoneResponse(BaseSchema):
    id: int
    user_id: UserId
    name: Name
    lat: Latitude
    lon: Longitude
    radius_m: RadiusM
    created_at: datetime
    updated_at: datetime
