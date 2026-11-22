"""Configuración centralizada de la aplicación mediante variables de entorno."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parámetros de configuración validados al iniciar la aplicación."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Despensa API"
    environment: Literal["local", "dev", "prod"] = "local"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://localhost:5432/despensa"
    rabbitmq_url: str = "amqp://localhost:5672/"

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_from_email: str = "no-reply@despensa.local"

    # Seguridad JWT: debe inyectarse vía .env o Secrets Manager (>= 32 caracteres)
    jwt_secret_key: str = Field(default="", repr=False)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Outbox Relay, Scheduler y Rate Limiting
    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 50
    outbox_max_attempts: int = 5
    auth_rate_limit_max_attempts: int = 10
    auth_rate_limit_window_seconds: int = 60
    expiration_scan_interval_seconds: float = 3600.0

    # Configuración de AWS / LocalStack / AWS Emulator
    aws_endpoint_url: str | None = None
    aws_default_region: str = "us-east-1"
    aws_access_key_id: str = "mock_key"
    aws_secret_access_key: str = Field(default="mock_secret", repr=False)
    s3_bucket_name: str = "despensa-media-local"


@lru_cache
def get_settings() -> Settings:
    """Retorna la instancia cacheada de configuración."""
    return Settings()
