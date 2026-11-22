"""Excepciones de dominio para el módulo pantry mapeadas a RFC 7807."""

from fastapi import status

from app.core.exceptions import DomainError


class PantryNotFoundError(DomainError):
    """La despensa solicitada no existe."""

    status_code = status.HTTP_404_NOT_FOUND
    error_type = "pantry-not-found"
    title = "Pantry Not Found"


class PantryAccessDeniedError(DomainError):
    """El usuario no es miembro de la despensa (Escudo de protección IDOR)."""

    status_code = status.HTTP_403_FORBIDDEN
    error_type = "pantry-access-denied"
    title = "Pantry Access Denied"


class LocationNotFoundError(DomainError):
    """La ubicación física no existe o no pertenece a esta despensa."""

    status_code = status.HTTP_404_NOT_FOUND
    error_type = "location-not-found"
    title = "Location Not Found"


class ProductNotFoundError(DomainError):
    """El producto no existe en el catálogo maestro."""

    status_code = status.HTTP_404_NOT_FOUND
    error_type = "product-not-found"
    title = "Product Not Found"


class UnitNotFoundError(DomainError):
    """La unidad de medida no es válida o no existe en el catálogo canónico."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "unit-not-found"
    title = "Unit Not Found"


class InsufficientStockError(DomainError):
    """No hay suficiente stock disponible para consumir la cantidad solicitada."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "insufficient-stock"
    title = "Insufficient Stock"


class InvalidInviteCodeError(DomainError):
    """El código de invitación ingresado no existe o no es válido."""

    status_code = status.HTTP_404_NOT_FOUND
    error_type = "invalid-invite-code"
    title = "Invalid Invite Code"


class AlreadyPantryMemberError(DomainError):
    """El usuario ya es miembro activo de esta despensa."""

    status_code = status.HTTP_409_CONFLICT
    error_type = "already-pantry-member"
    title = "Already Pantry Member"
