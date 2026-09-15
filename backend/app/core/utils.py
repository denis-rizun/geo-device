from pathlib import Path
from typing import Annotated

from geoalchemy2 import Geography
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
BASE_MODEL_CONFIG = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore", env_file_encoding="utf-8")
FRONTEND_DIR = BASE_DIR.parent / "frontend"

SRID = 4326
GEOGRAPHY_POINT = Geography(geometry_type="POINT", srid=SRID, spatial_index=False)

Latitude = Annotated[float, Field(ge=-90.0, le=90.0)]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]
MAX_ID_LENGTH = 64
DeviceId = Annotated[str, Field(min_length=1, max_length=MAX_ID_LENGTH)]
UserId = Annotated[str, Field(min_length=1, max_length=MAX_ID_LENGTH)]


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
