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
        ("/api/v1/pantries", "422", {"validation-error", "idempotency-key-reused"}),
    ],
)
def test_mutations_document_their_problem_types(
    openapi: dict[str, Any],
    path: str,
    status: str,
    expected: set[str],
) -> None:
    assert _types(openapi, path, status) == expected


def _operations(openapi: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (path, method, op)
        for path, item in openapi["paths"].items()
        for method, op in item.items()
        if isinstance(op, dict) and "responses" in op
    ]


def test_every_422_is_problem_json_with_validation_error(openapi: dict[str, Any]) -> None:
    """Issue #21: un solo media type para el 422 en todo el contrato."""
    with_422 = [(p, m, op) for p, m, op in _operations(openapi) if "422" in op["responses"]]
    assert with_422
    for path, method, op in with_422:
        content = op["responses"]["422"]["content"]
        assert list(content) == ["application/problem+json"], (method, path)
        schema = content["application/problem+json"]["schema"]
        assert ERRORS + "validation-error" in schema["properties"]["type"]["enum"], (method, path)
        assert "errors" in schema["properties"]
    assert "HTTPValidationError" not in openapi["components"]["schemas"]


def test_422_of_idempotent_mutations_keeps_key_reused(openapi: dict[str, Any]) -> None:
    assert _types(openapi, "/api/v1/pantries/join", "422") == {
        "validation-error",
        "idempotency-key-reused",
    }


def test_every_bearer_operation_documents_401(openapi: dict[str, Any]) -> None:
    """Issue #21: 401 en todas las rutas que exigen Bearer."""
    secured = [(p, m, op) for p, m, op in _operations(openapi) if op.get("security")]
    assert len(secured) >= 16
    for path, method, op in secured:
        enum = op["responses"]["401"]["content"]["application/problem+json"]["schema"][
            "properties"
        ]["type"]["enum"]
        assert ERRORS + "invalid-token" in enum, (method, path)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/v1/auth/login", {"invalid-credentials"}),
        ("/api/v1/auth/refresh", {"invalid-token"}),
        ("/api/v1/auth/logout", {"invalid-token"}),
    ],
)
def test_auth_routes_document_their_401(
    openapi: dict[str, Any], path: str, expected: set[str]
) -> None:
    assert _types(openapi, path, "401") == expected


def test_dashboard_documents_403_401_and_422(openapi: dict[str, Any]) -> None:
    path = "/api/v1/pantries/{pantry_id}/dashboard"
    responses = openapi["paths"][path]["get"]["responses"]
    assert {"200", "401", "403", "422"} <= set(responses)
