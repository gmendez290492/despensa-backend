"""Documentación OpenAPI de los errores RFC 7807 (problem+json) de la API.

- `problem_responses(*errores)`: agrupa excepciones de dominio por status con su `type` como enum.
- `install_openapi(app, ...)`: post-procesa el esquema generado por FastAPI para que el
  contrato refleje lo que la API devuelve de verdad (issue #21):
  * 401 en todas las operaciones con seguridad Bearer.
  * 422 siempre como `application/problem+json` (`validation-error`, con la extensión
    `errors`), en lugar del `HTTPValidationError` por defecto de FastAPI.
"""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from fastapi import FastAPI

from app.core.exceptions import ERRORS_BASE_URI, VALIDATION_ERROR_TYPE, DomainError

PROBLEM_MEDIA_TYPE = "application/problem+json"

_PROBLEM_PROPERTIES: dict[str, Any] = {
    "title": {"type": "string"},
    "status": {"type": "integer"},
    "detail": {"type": "string"},
    "instance": {"type": "string"},
    "correlation_id": {"type": ["string", "null"]},
}

_FIELD_ERRORS_PROPERTY: dict[str, Any] = {
    "type": "array",
    "description": "Solo en `validation-error`: un elemento por campo inválido.",
    "items": {
        "type": "object",
        "required": ["loc", "msg"],
        "properties": {
            "loc": {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
            "msg": {"type": "string"},
            "type": {"type": "string"},
        },
    },
}

_VALIDATION_NOTE = "cuerpo, ruta o query inválidos; `errors` detalla cada campo"


def _type_uri(error_type: str) -> str:
    return f"{ERRORS_BASE_URI}{error_type}"


def _problem_content(type_uris: list[str], *, field_errors: bool = False) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "type": {"type": "string", "enum": type_uris},
        **_PROBLEM_PROPERTIES,
    }
    if field_errors:
        properties["errors"] = _FIELD_ERRORS_PROPERTY
    return {
        PROBLEM_MEDIA_TYPE: {
            "schema": {
                "type": "object",
                "description": "RFC 7807 (problem+json).",
                "required": ["type", "title", "status"],
                "properties": properties,
            },
        },
    }


def problem_responses(
    *errors: type[DomainError],
    notes: Mapping[type[DomainError], str] | None = None,
) -> dict[int | str, dict[str, Any]]:
    """Respuestas OpenAPI de las excepciones de dominio que puede lanzar una operación.

    Agrupa por status y documenta cada `type` posible como enum, con una línea de
    descripción por error (`notes` o, si no hay, el `title` de la excepción).
    """
    by_status: dict[int, list[type[DomainError]]] = {}
    for error in errors:
        group = by_status.setdefault(error.status_code, [])
        if error not in group:
            group.append(error)

    notes = notes or {}
    return {
        code: {
            "description": "\n".join(
                f"- `{e.error_type}`: {notes.get(e, e.title)}" for e in by_status[code]
            ),
            "content": _problem_content([_type_uri(e.error_type) for e in by_status[code]]),
        }
        for code in sorted(by_status)
    }


def _existing_types(response: Mapping[str, Any]) -> list[str]:
    schema = response.get("content", {}).get(PROBLEM_MEDIA_TYPE, {}).get("schema", {})
    enum = schema.get("properties", {}).get("type", {}).get("enum", [])
    return list(enum)


def _merge_problem(
    responses: dict[str, Any],
    code: str,
    type_uris: Iterable[str],
    lines: Iterable[str],
    *,
    field_errors: bool = False,
) -> None:
    current = responses.get(code, {})
    types = _existing_types(current)
    for uri in type_uris:
        if uri not in types:
            types.append(uri)
    description_lines = [
        line for line in str(current.get("description", "")).splitlines() if line.startswith("- `")
    ]
    for line in lines:
        if line not in description_lines:
            description_lines.append(line)
    responses[code] = {
        "description": "\n".join(description_lines),
        "content": _problem_content(types, field_errors=field_errors),
    }


def _postprocess(schema: dict[str, Any], bearer_errors: tuple[type[DomainError], ...]) -> None:
    validation_uri = _type_uri(VALIDATION_ERROR_TYPE)
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            responses: dict[str, Any] = operation["responses"]

            if operation.get("security"):
                _merge_problem(
                    responses,
                    "401",
                    [_type_uri(e.error_type) for e in bearer_errors],
                    [f"- `{e.error_type}`: {e.title}" for e in bearer_errors],
                )

            if "422" in responses:
                _merge_problem(
                    responses,
                    "422",
                    [validation_uri],
                    [f"- `{VALIDATION_ERROR_TYPE}`: {_VALIDATION_NOTE}"],
                    field_errors=True,
                )

    # Sin referencias, los esquemas de validación por defecto de FastAPI sobran.
    components = schema.get("components", {}).get("schemas", {})
    serialized = str(schema.get("paths", {}))
    for name in ("HTTPValidationError", "ValidationError"):
        if f"#/components/schemas/{name}" not in serialized:
            components.pop(name, None)


def install_openapi(app: FastAPI, *, bearer_errors: tuple[type[DomainError], ...]) -> None:
    """Sustituye `app.openapi` por la versión post-procesada (se calcula una sola vez)."""
    generate: Callable[[], dict[str, Any]] = app.openapi
    done = False

    def openapi() -> dict[str, Any]:
        nonlocal done
        schema = generate()
        if not done:
            _postprocess(schema, bearer_errors)
            done = True
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
