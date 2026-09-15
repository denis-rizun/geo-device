from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.utils import BASE_MODEL_CONFIG


class IngestSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_MODEL_CONFIG, env_prefix="INGEST_")

    WORKERS: int = 4
    CHUNK_SIZE: int = 500
    MAX_HTTP_BATCH_SIZE: int = 1_000
    BACKLOG_LIMIT: int = 200_000
    STREAM_MAX_LEN: int = 4_000
    DRAIN_TIMEOUT_S: float = 10.0
    ZONE_ENTRY_TTL_S: int = 60
    POSITION_FLUSH_INTERVAL_S: float = 1.0
    MAX_PING_AGE_S: int = 86_400
    MAX_PING_SKEW_S: int = 300
    RETENTION_DAYS: int = 7
    RETENTION_INTERVAL_S: float = 3600.0
    RETENTION_BATCH_SIZE: int = 50_000


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_MODEL_CONFIG, env_prefix="REDIS_")

    HOST: str = "localhost"
    PORT: int = 6379
    DB: int = 0
    SOCKET_TIMEOUT_S: float = 5.0
    CONNECT_TIMEOUT_S: float = 5.0
    HEALTHCHECK_TIMEOUT_S: float = 3.0

    TEST_HOST: str = "localhost"
    TEST_DB: int = 15

    def get_url(self) -> str:
        return f"redis://{self.HOST}:{self.PORT}/{self.DB}"

    def get_test_url(self) -> str:
        return f"redis://{self.TEST_HOST}:{self.PORT}/{self.TEST_DB}"
