"""Excepciones de dominio para el módulo recipes mapeadas a RFC 7807."""

from fastapi import status

from app.core.exceptions import DomainError


class RecipeNotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    error_type = "recipe-not-found"
    title = "Receta no encontrada"

    def __init__(self, recipe_id: str) -> None:
        super().__init__(detail=f"La receta con ID '{recipe_id}' no existe en el catálogo.")
