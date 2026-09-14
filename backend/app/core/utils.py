from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
BASE_MODEL_CONFIG = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore", env_file_encoding="utf-8")

Latitude = Annotated[float, Field(ge=-90.0, le=90.0)]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]
DeviceId = Annotated[str, Field(min_length=1, max_length=64)]
UserId = Annotated[str, Field(min_length=1, max_length=64)]


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
