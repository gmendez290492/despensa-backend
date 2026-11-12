"""Configuración centralizada de la aplicación mediante variables de entorno."""

from functools import lru_cache
from typing import Literal

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


@lru_cache
def get_settings() -> Settings:
    """Retorna la instancia cacheada de configuración."""
    return Settings()
