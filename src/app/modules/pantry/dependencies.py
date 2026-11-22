"""Inyección de dependencias para el módulo pantry."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.modules.pantry.service import PantryService


async def get_pantry_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PantryService:
    """Provee la instancia de PantryService inyectando la sesión de BD activa."""
    return PantryService(session)


PantryServiceDep = Annotated[PantryService, Depends(get_pantry_service)]
