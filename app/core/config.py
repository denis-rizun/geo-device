import logging
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.utils import BASE_MODEL_CONFIG
from app.pipeline.config import IngestSettings, RedisSettings
from app.realtime.config import RealtimeSettings


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_MODEL_CONFIG, env_prefix="API_")

    NAME: str = "GEO Device"
    VERSION: str = "1.0.0"
    PORT: int = 8000
    WORKERS: int = 1
    ALLOWED_HOSTS: list[str] = ["http://localhost:3000"]
    ALLOW_CREDENTIALS: bool = True
    ALLOWED_METHODS: list[str] = ["*"]
    ALLOWED_HEADERS: list[str] = ["*"]


class LoggerSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_MODEL_CONFIG, env_prefix="LOGGING_")

    LEVEL: int = 0
    LEVEL_NAME: str = "INFO"

    @model_validator(mode="after")
    def set_level(self) -> Self:
        self.LEVEL = logging.getLevelNamesMapping().get(self.LEVEL_NAME.upper(), logging.INFO)
        return self


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_MODEL_CONFIG, env_prefix="POSTGRES_")

    DATABASE: str = ""
    USER: str = ""
    PASSWORD: SecretStr = SecretStr("")
    HOST: str = ""
    PORT: int = 0
    POOL_SIZE: int = 5
    MAX_OVERFLOW: int = 10

    TEST_DATABASE: str = ""

    def get_url(self, driver: str | None = "asyncpg", is_test: bool = False) -> str:
        database = self.TEST_DATABASE if is_test else self.DATABASE
        return self._build_url(self.HOST, database, driver)

    def get_test_url(self, driver: str | None = "asyncpg") -> str:
        return self._build_url(self.HOST, self.TEST_DATABASE, driver)

    def _build_url(self, host: str, database: str, driver: str | None) -> str:
        driver = f"+{driver}" if driver else ""
        return f"postgresql{driver}://{self.USER}:{self.PASSWORD.get_secret_value()}@{host}:{self.PORT}/{database}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_MODEL_CONFIG)

    ENV: Literal["DEV", "PROD"] = "DEV"
    api: APISettings = Field(default_factory=APISettings)
    logging: LoggerSettings = Field(default_factory=LoggerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    ingest: IngestSettings = Field(default_factory=IngestSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    realtime: RealtimeSettings = Field(default_factory=RealtimeSettings)

    @classmethod
    @lru_cache
    def get_instance(cls) -> Self:
        return cls()


config = Settings.get_instance()
