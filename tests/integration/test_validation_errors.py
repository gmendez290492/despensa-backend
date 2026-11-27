"""Los 422 de validación son problem+json `validation-error` (issue #21)."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.integration.test_pantry_and_fefo import get_auth_token_for_user

VALIDATION = "https://despensa.api/errors/validation-error"


@pytest.mark.asyncio
async def test_invalid_body_returns_problem_json_without_echoing_input(
    api_client: AsyncClient,
) -> None:
    res = await api_client.post(
        "/api/v1/auth/register",
        json={"email": "no-es-un-correo", "password": "corta-pero-secreta", "full_name": "A"},
        headers={"X-Correlation-ID": "corr-422"},
    )

    assert res.status_code == 422
    assert res.headers["content-type"].startswith("application/problem+json")
    body = res.json()
    assert body["type"] == VALIDATION
    assert body["status"] == 422
    assert body["instance"] == "/api/v1/auth/register"
    assert body["correlation_id"] == "corr-422"
    locs = [err["loc"] for err in body["errors"]]
    assert ["body", "email"] in locs
    assert all(set(err) <= {"loc", "msg", "type"} for err in body["errors"])
    assert "corta-pero-secreta" not in res.text  # no se devuelve el input
    assert body["detail"] == body["errors"][0]["msg"]


@pytest.mark.asyncio
async def test_invalid_path_param_returns_problem_json(api_client: AsyncClient) -> None:
    token = await get_auth_token_for_user(api_client, f"val_{uuid4().hex[:8]}@example.com", "Val")

    res = await api_client.get(
        "/api/v1/pantries/no-es-uuid/dashboard",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert res.status_code == 422
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["errors"][0]["loc"] == ["path", "pantry_id"]
