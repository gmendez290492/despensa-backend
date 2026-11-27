"""Rutas HTTP (/api/v1/pantries, /api/v1/products, /api/v1/categories) del módulo pantry."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.core.idempotency import IDEMPOTENCY_RESPONSES, IdempotencyDep
from app.modules.pantry.dependencies import PantryServiceDep
from app.modules.pantry.schemas import (
    CategoryResponse,
    ConsumeRequest,
    ConsumeResultResponse,
    FoodBatchCreateRequest,
    FoodBatchResponse,
    LocationCreateRequest,
    LocationResponse,
    PantryCreateRequest,
    PantryJoinRequest,
    PantryResponse,
    ProductCreateRequest,
    ProductResponse,
)
from app.modules.users.dependencies import get_current_user
from app.modules.users.models import User

router = APIRouter(prefix="/api/v1", tags=["pantry"])

CurrentUserDep = Annotated[User, Depends(get_current_user)]


# --- DESPENSAS / HOGARES (MULTI-TENANCY) ---


@router.post(
    "/pantries",
    response_model=PantryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una nueva despensa",
    responses=IDEMPOTENCY_RESPONSES,
)
async def create_pantry(
    request: Request,
    payload: PantryCreateRequest,
    current_user: CurrentUserDep,
    service: PantryServiceDep,
    idempotency: IdempotencyDep,
) -> PantryResponse | JSONResponse:
    """Crea una despensa y convierte al usuario autenticado en su OWNER."""
    correlation_id = getattr(request.state, "correlation_id", "")

    async def action() -> PantryResponse:
        pantry = await service.create_pantry(
            payload,
            user_id=current_user.id,
            correlation_id=correlation_id,
        )
        return PantryResponse.model_validate(pantry)

    return await idempotency.run(
        user_id=current_user.id,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        service=service,
        action=action,
    )


@router.get(
    "/pantries",
    response_model=list[PantryResponse],
    summary="Listar mis despensas",
)
async def list_pantries(
    current_user: CurrentUserDep,
    service: PantryServiceDep,
) -> list[PantryResponse]:
    """Retorna todas las despensas donde el usuario es miembro activo."""
    pantries = await service.list_my_pantries(user_id=current_user.id)
    return [PantryResponse.model_validate(p) for p in pantries]


@router.post(
    "/pantries/join",
    response_model=PantryResponse,
    summary="Unirse a una despensa mediante código de invitación",
    responses=IDEMPOTENCY_RESPONSES,
)
async def join_pantry(
    request: Request,
    payload: PantryJoinRequest,
    current_user: CurrentUserDep,
    service: PantryServiceDep,
    idempotency: IdempotencyDep,
) -> PantryResponse | JSONResponse:
    """Permite compartir una despensa uniendo al usuario con rol de miembro."""
    correlation_id = getattr(request.state, "correlation_id", "")

    async def action() -> PantryResponse:
        pantry = await service.join_pantry(
            payload.invite_code,
            user_id=current_user.id,
            correlation_id=correlation_id,
        )
        return PantryResponse.model_validate(pantry)

    return await idempotency.run(
        user_id=current_user.id,
        payload=payload,
        status_code=status.HTTP_200_OK,
        service=service,
        action=action,
    )


# --- UBICACIONES FÍSICAS ---


@router.post(
    "/pantries/{pantry_id}/locations",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear zona de almacenamiento en la despensa",
    responses=IDEMPOTENCY_RESPONSES,
)
async def create_location(
    pantry_id: UUID,
    payload: LocationCreateRequest,
    current_user: CurrentUserDep,
    service: PantryServiceDep,
    idempotency: IdempotencyDep,
) -> LocationResponse | JSONResponse:
    """Crea una ubicación física (Refrigerador, Congelador, Alacena) protegida por IDOR."""

    async def action() -> LocationResponse:
        location = await service.create_location(
            pantry_id=pantry_id,
            data=payload,
            user_id=current_user.id,
        )
        return LocationResponse.model_validate(location)

    return await idempotency.run(
        user_id=current_user.id,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        service=service,
        action=action,
    )


@router.get(
    "/pantries/{pantry_id}/locations",
    response_model=list[LocationResponse],
    summary="Listar zonas de una despensa",
)
async def list_locations(
    pantry_id: UUID,
    current_user: CurrentUserDep,
    service: PantryServiceDep,
) -> list[LocationResponse]:
    """Lista las ubicaciones de la despensa tras verificar membresía (IDOR)."""
    locations = await service.list_locations(pantry_id=pantry_id, user_id=current_user.id)
    return [LocationResponse.model_validate(loc) for loc in locations]


# --- CATÁLOGO DE PRODUCTOS Y CATEGORÍAS ---


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    summary="Listar categorías de alimentos",
)
async def list_categories(
    service: PantryServiceDep,
) -> list[CategoryResponse]:
    """Retorna las categorías maestras de alimentos."""
    categories = await service.pantry_repo.list_categories()
    return [CategoryResponse.model_validate(c) for c in categories]


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear producto en el catálogo maestro",
    responses=IDEMPOTENCY_RESPONSES,
)
async def create_product(
    payload: ProductCreateRequest,
    current_user: CurrentUserDep,
    service: PantryServiceDep,
    idempotency: IdempotencyDep,
) -> ProductResponse | JSONResponse:
    """Registra un producto maestro genérico."""

    async def action() -> ProductResponse:
        product = await service.create_product(payload)
        return ProductResponse.model_validate(product)

    return await idempotency.run(
        user_id=current_user.id,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        service=service,
        action=action,
    )


@router.get(
    "/products",
    response_model=list[ProductResponse],
    summary="Buscar productos en el catálogo",
)
async def list_products(
    service: PantryServiceDep,
    category_id: UUID | None = None,
    q: str | None = Query(default=None, description="Término de búsqueda"),
) -> list[ProductResponse]:
    """Busca productos por categoría o por texto."""
    products = await service.pantry_repo.list_products(category_id=category_id, search=q)
    return [ProductResponse.model_validate(p) for p in products]


# --- LOTES DE ALIMENTO E INVENTARIO FEFO ---


@router.post(
    "/pantries/{pantry_id}/batches",
    response_model=FoodBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar compra de lote de alimento",
    responses=IDEMPOTENCY_RESPONSES,
)
async def add_food_batch(
    request: Request,
    pantry_id: UUID,
    payload: FoodBatchCreateRequest,
    current_user: CurrentUserDep,
    service: PantryServiceDep,
    idempotency: IdempotencyDep,
) -> FoodBatchResponse | JSONResponse:
    """Agrega un lote físico con fecha de expiración calculando semáforo en tiempo real."""
    correlation_id = getattr(request.state, "correlation_id", "")
    return await idempotency.run(
        user_id=current_user.id,
        payload=payload,
        status_code=status.HTTP_201_CREATED,
        service=service,
        action=lambda: service.add_food_batch(
            pantry_id=pantry_id,
            data=payload,
            user_id=current_user.id,
            correlation_id=correlation_id,
        ),
    )


@router.get(
    "/pantries/{pantry_id}/batches",
    response_model=list[FoodBatchResponse],
    summary="Listar lotes disponibles con semáforo de vencimiento",
)
async def list_batches(
    pantry_id: UUID,
    current_user: CurrentUserDep,
    service: PantryServiceDep,
) -> list[FoodBatchResponse]:
    """Lista todos los alimentos físicos disponibles ordenados por FEFO."""
    return await service.list_pantry_batches(pantry_id=pantry_id, user_id=current_user.id)


@router.post(
    "/pantries/{pantry_id}/consume",
    response_model=ConsumeResultResponse,
    summary="Consumir alimento aplicando algoritmo FEFO inteligente",
    responses=IDEMPOTENCY_RESPONSES,
)
async def consume_product(
    request: Request,
    pantry_id: UUID,
    payload: ConsumeRequest,
    current_user: CurrentUserDep,
    service: PantryServiceDep,
    idempotency: IdempotencyDep,
) -> ConsumeResultResponse | JSONResponse:
    """Descuenta stock automáticamente del lote que vence más pronto (First Expired, First Out).

    Con `Idempotency-Key`, un reintento devuelve el resultado original sin volver a descontar.
    """
    correlation_id = getattr(request.state, "correlation_id", "")
    return await idempotency.run(
        user_id=current_user.id,
        payload=payload,
        status_code=status.HTTP_200_OK,
        service=service,
        action=lambda: service.consume_product_fefo(
            pantry_id=pantry_id,
            data=payload,
            user_id=current_user.id,
            correlation_id=correlation_id,
        ),
    )
