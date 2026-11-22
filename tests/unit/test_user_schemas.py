"""Pruebas unitarias de validación en esquemas Pydantic de usuarios."""

import pytest
from pydantic import ValidationError

from app.modules.users.schemas import UserRegisterRequest


def test_register_schema_normalizes_and_validates() -> None:
    """Verifica normalización de email/nombre y zona horaria IANA válida."""
    req = UserRegisterRequest(
        email="  Gerardo@Example.COM ",
        password="Password123!",
        full_name="  Gerardo Mendez  ",
        timezone="America/Mexico_City",
        alert_days_before=5,
    )

    assert req.email == "gerardo@example.com"
    assert req.full_name == "Gerardo Mendez"
    assert req.timezone == "America/Mexico_City"
    assert req.alert_days_before == 5


def test_register_schema_rejects_invalid_timezone() -> None:
    """Verifica rechazo de zonas horarias inexistentes."""
    with pytest.raises(ValidationError):
        UserRegisterRequest(
            email="ana@example.com",
            password="Password123!",
            full_name="Ana Lopez",
            timezone="Mars/Olympus",
        )


def test_register_schema_rejects_short_password_and_extra_fields() -> None:
    """Verifica largo mínimo de contraseña y rechazo de campos inesperados."""
    with pytest.raises(ValidationError):
        UserRegisterRequest(
            email="ana@example.com",
            password="short",
            full_name="Ana Lopez",
        )

    with pytest.raises(ValidationError):
        UserRegisterRequest.model_validate(
            {
                "email": "ana@example.com",
                "password": "Password123!",
                "full_name": "Ana Lopez",
                "is_admin": True,
            },
        )
