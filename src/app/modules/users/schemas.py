"""Esquemas Pydantic (contratos DTO) del módulo users."""

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRegisterRequest(BaseModel):
    """Datos requeridos para registrar una cuenta nueva."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    timezone: str = Field(default="UTC", max_length=64)
    alert_days_before: int = Field(default=3, ge=1, le=30)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        """Normaliza el correo electrónico en minúsculas."""
        return str(value).strip().lower()

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        """Elimina espacios sobrantes del nombre completo."""
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres.")
        return cleaned

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Verifica que la zona horaria exista en la base IANA."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Zona horaria IANA inválida: {value}") from exc
        return value


class UserLoginRequest(BaseModel):
    """Credenciales para iniciar sesión."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        """Normaliza el correo electrónico en minúsculas."""
        return str(value).strip().lower()


class RefreshTokenRequest(BaseModel):
    """Petición para rotar el par de tokens usando el refresh token."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=10)


class UserResponse(BaseModel):
    """Representación pública segura de un usuario (sin password_hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    timezone: str
    alert_days_before: int
    created_at: datetime


class TokenResponse(BaseModel):
    """Par de tokens JWT devuelto tras login o refresh."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int


class PasswordForgotRequest(BaseModel):
    """Solicitud de correo para restablecer la contraseña."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        """Normaliza el correo electrónico en minúsculas."""
        return str(value).strip().lower()


class PasswordResetRequest(BaseModel):
    """Token recibido por correo y nueva contraseña."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    """Respuesta genérica con un mensaje legible."""

    detail: str
