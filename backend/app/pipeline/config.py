from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.utils import BASE_MODEL_CONFIG


class IngestSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_MODEL_CONFIG, env_prefix="INGEST_")

    WORKERS: int = 4
    CHUNK_SIZE: int = 500
    MAX_HTTP_BATCH_SIZE: int = 1_000
    BACKLOG_LIMIT: int = 10_000
    STREAM_MAX_LEN: int = 1_000_000
    DRAIN_TIMEOUT_S: float = 10.0


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_MODEL_CONFIG, env_prefix="REDIS_")

    HOST: str = "localhost"
    PORT: int = 6379
    DB: int = 0

    def get_url(self) -> str:
        return f"redis://{self.HOST}:{self.PORT}/{self.DB}"
