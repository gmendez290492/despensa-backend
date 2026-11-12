"""Pruebas unitarias para los endpoints de salud (/health/live y /health/ready)."""

from fastapi.testclient import TestClient

from app.core.health import HealthCheckFn
from app.main import create_app, get_db_check, get_rabbitmq_check


def _always_ok() -> HealthCheckFn:
    async def _check() -> bool:
        return True

    return _check


def _always_fail() -> HealthCheckFn:
    async def _check() -> bool:
        return False

    return _check


def test_root_endpoint() -> None:
    """Verifica el endpoint raíz con enlace a Swagger."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["docs"] == "/docs"
    assert body["version"] == "0.1.0"


def test_health_live() -> None:
    """Verifica que /health/live responde 200 cuando el proceso está activo."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_ready_all_ok() -> None:
    """Verifica que /health/ready responde 200 cuando DB y RabbitMQ responden."""
    app = create_app()
    app.dependency_overrides[get_db_check] = _always_ok
    app.dependency_overrides[get_rabbitmq_check] = _always_ok

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"postgres": "ok", "rabbitmq": "ok"},
    }


def test_health_ready_degraded_when_dependency_fails() -> None:
    """Verifica que /health/ready responde 503 si falla una dependencia."""
    app = create_app()
    app.dependency_overrides[get_db_check] = _always_ok
    app.dependency_overrides[get_rabbitmq_check] = _always_fail

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "checks": {"postgres": "ok", "rabbitmq": "error"},
    }
