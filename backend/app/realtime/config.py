from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.utils import BASE_MODEL_CONFIG


class RealtimeSettings(BaseSettings):
    model_config = SettingsConfigDict(**BASE_MODEL_CONFIG, env_prefix="REALTIME_")

    QUEUE_SIZE: int = 64
