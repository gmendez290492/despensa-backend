"""Esquemas Pydantic v2 (DTOs) del módulo pantry."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class PantryCreateRequest(BaseModel):
    """Datos para crear una despensa nueva (el creador se convierte en 'owner')."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("El nombre de la despensa debe tener al menos 2 caracteres.")
        return cleaned


class PantryJoinRequest(BaseModel):
    """Código de invitación para unirse a una despensa existente."""

    model_config = ConfigDict(extra="forbid")

    invite_code: str = Field(min_length=6, max_length=32)

    @field_validator("invite_code")
    @classmethod
    def clean_code(cls, value: str) -> str:
        return value.strip().upper()


class PantryResponse(BaseModel):
    """Representación pública de una despensa."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    invite_code: str
    created_at: datetime


class PantryMemberResponse(BaseModel):
    """Información de un miembro y su rol dentro de la despensa."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pantry_id: UUID
    user_id: UUID
    role: Literal["owner", "admin", "member"]
    joined_at: datetime


class LocationCreateRequest(BaseModel):
    """Datos para crear una zona de almacenamiento físico."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=64)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("El nombre de la ubicación debe tener al menos 2 caracteres.")
        return cleaned


class LocationResponse(BaseModel):
    """Representación pública de una ubicación física."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pantry_id: UUID
    name: str
    description: str | None
    created_at: datetime


class CategoryResponse(BaseModel):
    """Categoría del catálogo."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    icon: str | None


class ProductCreateRequest(BaseModel):
    """Creación o registro de un producto en el catálogo maestro."""

    model_config = ConfigDict(extra="forbid")

    category_id: UUID
    name: str = Field(min_length=2, max_length=120)
    barcode: str | None = Field(default=None, max_length=64)
    base_unit_code: str = Field(min_length=1, max_length=16)
    estimated_shelf_life_days: int = Field(default=7, ge=1, le=3650)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("base_unit_code")
    @classmethod
    def clean_unit(cls, value: str) -> str:
        return value.strip().lower()


class ProductResponse(BaseModel):
    """Representación pública de un producto."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    name: str
    barcode: str | None
    base_unit_code: str
    estimated_shelf_life_days: int


class FoodBatchCreateRequest(BaseModel):
    """Registro de una compra física o lote de alimento en una ubicación."""

    model_config = ConfigDict(extra="forbid")

    location_id: UUID
    product_id: UUID
    unit_code: str = Field(min_length=1, max_length=16)
    quantity: Decimal = Field(gt=Decimal("0"))
    expiration_date: date
    purchase_date: date = Field(default_factory=date.today)
    unit_cost: Decimal | None = Field(default=None, ge=Decimal("0"))

    @field_validator("unit_code")
    @classmethod
    def clean_unit(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("expiration_date")
    @classmethod
    def validate_dates(cls, expiration: date, info: ValidationInfo) -> date:
        purchase = info.data.get("purchase_date")
        if purchase and expiration < purchase:
            raise ValueError("La fecha de vencimiento no puede ser anterior a la fecha de compra.")
        return expiration


class FoodBatchResponse(BaseModel):
    """Detalle de un lote físico con cálculo dinámico de semáforo de vencimiento."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    location_id: UUID
    product_id: UUID
    product_name: str
    unit_code: str
    initial_quantity: Decimal
    current_quantity: Decimal
    expiration_date: date
    purchase_date: date
    unit_cost: Decimal | None
    status: Literal["available", "consumed", "expired"]
    dias_para_vencer: int
    semaforo: Literal["VENCIDO", "CRÍTICO", "PRECAUCIÓN", "ÓPTIMO"]


class ConsumeRequest(BaseModel):
    """Petición para consumir stock de un producto aplicando algoritmo FEFO."""

    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity: Decimal = Field(gt=Decimal("0"))
    notes: str | None = Field(default=None, max_length=255)


class BatchConsumeDetail(BaseModel):
    """Detalle de cuánto se descontó de un lote específico."""

    batch_id: UUID
    expiration_date: date
    quantity_deducted: Decimal
    batch_exhausted: bool


class ConsumeResultResponse(BaseModel):
    """Resultado del consumo inteligente FEFO a través de los lotes."""

    product_id: UUID
    requested_quantity: Decimal
    consumed_quantity: Decimal
    remaining_stock: Decimal
    batches_affected: list[BatchConsumeDetail]
