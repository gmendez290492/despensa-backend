"""Guardas de rendimiento por petición (issue #16)."""

import inspect
from collections.abc import Iterator
from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import create_app


def _is_async(call: Any) -> bool:
    if inspect.iscoroutinefunction(call) or inspect.isasyncgenfunction(call):
        return True
    # Instancias invocables como HTTPBearer: lo que cuenta es su método __call__.
    return not inspect.isclass(call) and inspect.iscoroutinefunction(type(call).__call__)


def _api_routes(routes: Any) -> Iterator[APIRoute]:
    """Rutas de la app, incluidas las de routers anidados (`_IncludedRouter` en FastAPI 0.165)."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _api_routes(inner.routes)


def _walk(dependant: Dependant) -> Iterator[Dependant]:
    for sub in dependant.dependencies:
        yield sub
        yield from _walk(sub)


def test_route_dependencies_are_async() -> None:
    """FastAPI ejecuta cada dependencia síncrona en el threadpool: un salto de hilo por petición."""
    routes = list(_api_routes(create_app().routes))
    assert any("pantries" in route.path for route in routes)  # el recorrido ve los routers
    sync_deps = {
        f"{route.path} -> {getattr(dep.call, '__qualname__', dep.call)}"
        for route in routes
        for dep in _walk(route.dependant)
        if dep.call is not None and not _is_async(dep.call)
    }
    assert not sync_deps, sorted(sync_deps)


def test_correlation_id_is_echoed_and_generated() -> None:
    with TestClient(create_app()) as client:
        echoed = client.get("/health/live", headers={"X-Correlation-ID": "abc-123"})
        generated = client.get("/health/live")

    assert echoed.headers["X-Correlation-ID"] == "abc-123"
    assert len(generated.headers["X-Correlation-ID"]) == 36
    assert generated.headers["X-Content-Type-Options"] == "nosniff"
