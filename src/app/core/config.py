"""Configuración centralizada de la aplicación mediante variables de entorno."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
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

    # Ventana de gracia del refresh: el refresh anterior devuelve el mismo par sucesor
    # durante N segundos, solo si la sesión tiene X-Client-Binding y coincide (0 = desactivada).
    refresh_reuse_grace_seconds: int = 10

    # Recuperación de contraseña
    password_reset_token_expire_minutes: int = 30
    frontend_base_url: str = "http://localhost:3000"

    # Outbox Relay y Scheduler
    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 50
    outbox_max_attempts: int = 5
    expiration_scan_interval_seconds: float = 3600.0

    # Rate Limiting. "postgres" comparte contadores entre réplicas y sobrevive a deploys;
    # "memory" es por proceso y solo apto para pruebas o una única instancia.
    rate_limit_backend: Literal["memory", "postgres"] = "postgres"
    # Por IP en login, forgot-password y reset-password (ventana corta)
    auth_rate_limit_max_attempts: int = 10
    auth_rate_limit_window_seconds: int = 60
    # Por IP en registro (más estricto para frenar la enumeración vía 409)
    register_rate_limit_max_attempts: int = 5
    register_rate_limit_window_seconds: int = 3600
    # Por IP en refresh y logout. Más holgado: el BFF refresca con frecuencia, pero sin
    # límite un cliente puede saturar la BD con refresh tokens inválidos.
    refresh_rate_limit_max_attempts: int = 30
    refresh_rate_limit_window_seconds: int = 60
    # Por email (hash SHA-256) en login, registro y forgot-password
    auth_email_rate_limit_max_attempts: int = 10
    auth_email_rate_limit_window_seconds: int = 900

    # Backends del worker. Local: RabbitMQ + SMTP (Mailpit). AWS: SNS/SQS + SES.
    messaging_backend: Literal["rabbitmq", "aws"] = "rabbitmq"
    email_backend: Literal["smtp", "ses"] = "smtp"
    sns_topic_arn: str | None = None
    sqs_notifications_queue_url: str | None = None
    sqs_wait_time_seconds: int = Field(default=20, ge=0, le=20)
    sqs_max_messages: int = Field(default=10, ge=1, le=10)

    # Configuración de AWS / LocalStack / AWS Emulator
    aws_endpoint_url: str | None = None
    aws_default_region: str = "us-east-1"
    aws_access_key_id: str = "mock_key"
    aws_secret_access_key: str = Field(default="mock_secret", repr=False)
    s3_bucket_name: str = "despensa-media-local"

    @model_validator(mode="after")
    def _require_aws_messaging_targets(self) -> "Settings":
        if self.messaging_backend == "aws" and not (
            self.sns_topic_arn and self.sqs_notifications_queue_url
        ):
            raise ValueError(
                "MESSAGING_BACKEND=aws requiere SNS_TOPIC_ARN y SQS_NOTIFICATIONS_QUEUE_URL.",
            )
        return self

    def aws_static_credentials(self) -> tuple[str | None, str | None]:
        """Credenciales explícitas solo contra un emulador (AWS_ENDPOINT_URL). En ECS se
        devuelven None para que boto3 use las del rol de la tarea."""
        if self.aws_endpoint_url:
            return self.aws_access_key_id, self.aws_secret_access_key
        return None, None


@lru_cache
def get_settings() -> Settings:
    """Retorna la instancia cacheada de configuración."""
    return Settings()
