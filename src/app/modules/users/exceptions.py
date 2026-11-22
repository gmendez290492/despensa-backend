"""Excepciones de dominio del módulo users."""

from fastapi import status

from app.core.exceptions import DomainError


class EmailAlreadyExistsError(DomainError):
    """El correo electrónico ya está registrado."""

    status_code = status.HTTP_409_CONFLICT
    error_type = "email-already-exists"
    title = "Email Already Registered"


class InvalidCredentialsError(DomainError):
    """Correo o contraseña incorrectos, o usuario inactivo."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_type = "invalid-credentials"
    title = "Invalid Credentials"


class InvalidTokenError(DomainError):
    """Token JWT inválido, expirado o revocado."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_type = "invalid-token"
    title = "Invalid or Expired Token"


class UserNotFoundError(DomainError):
    """Usuario no encontrado."""

    status_code = status.HTTP_404_NOT_FOUND
    error_type = "user-not-found"
    title = "User Not Found"
