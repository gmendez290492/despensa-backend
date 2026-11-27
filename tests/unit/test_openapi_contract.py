"""El OpenAPI documenta todos los `type` problem+json que puede devolver cada mutación."""

from typing import Any

import pytest

from app.main import create_app

ERRORS = "https://despensa.api/errors/"


@pytest.fixture(scope="module")
def openapi() -> dict[str, Any]:
    schema: dict[str, Any] = create_app().openapi()
    return schema


def _types(openapi: dict[str, Any], path: str, status: str) -> set[str]:
    response = openapi["paths"][path]["post"]["responses"][status]
    enum = response["content"]["application/problem+json"]["schema"]["properties"]["type"]["enum"]
    return {t.removeprefix(ERRORS) for t in enum}


def test_join_409_lists_business_and_idempotency_conflicts(openapi: dict[str, Any]) -> None:
    """Issue #17: el 409 de /pantries/join también puede ser already-pantry-member."""
    assert _types(openapi, "/api/v1/pantries/join", "409") == {
        "already-pantry-member",
        "idempotency-request-in-progress",
    }
    assert _types(openapi, "/api/v1/pantries/join", "404") == {"invalid-invite-code"}


@pytest.mark.parametrize(
    ("path", "status", "expected"),
    [
        (
            "/api/v1/pantries/{pantry_id}/consume",
            "400",
            {"insufficient-stock", "invalid-idempotency-key"},
        ),
        ("/api/v1/pantries/{pantry_id}/consume", "403", {"pantry-access-denied"}),
        (
            "/api/v1/pantries/{pantry_id}/batches",
            "404",
            {"location-not-found", "product-not-found"},
        ),
        ("/api/v1/pantries/{pantry_id}/locations", "403", {"pantry-access-denied"}),
        ("/api/v1/products", "400", {"unit-not-found", "invalid-idempotency-key"}),
        ("/api/v1/pantries", "422", {"idempotency-key-reused"}),
    ],
)
def test_mutations_document_their_problem_types(
    openapi: dict[str, Any],
    path: str,
    status: str,
    expected: set[str],
) -> None:
    assert _types(openapi, path, status) == expected


def test_422_keeps_fastapi_validation_schema(openapi: dict[str, Any]) -> None:
    content = openapi["paths"]["/api/v1/pantries/join"]["post"]["responses"]["422"]["content"]
    assert (
        content["application/json"]["schema"]["$ref"] == "#/components/schemas/HTTPValidationError"
    )
