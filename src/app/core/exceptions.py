"""Excepciones base de dominio y manejador HTTP estándar RFC 7807."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Excepción base para reglas de negocio independientes del transporte HTTP."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_type: str = "domain-error"
    title: str = "Domain Error"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        self.headers: dict[str, str] = {}
        super().__init__(detail)


class RateLimitExceededError(DomainError):
    """Se lanza cuando un cliente excede el límite permitido de peticiones."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_type = "rate-limit-exceeded"
    title = "Too Many Requests"

    def __init__(self, detail: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(detail)
        if retry_after_seconds is not None:
            self.headers["Retry-After"] = str(max(1, retry_after_seconds))


def problem_details(request: Request, exc: DomainError) -> dict[str, object]:
    """Cuerpo RFC 7807 de un error de dominio (también se guarda para repetirlo)."""
    return {
        "type": f"https://despensa.api/errors/{exc.error_type}",
        "title": exc.title,
        "status": exc.status_code,
        "detail": exc.detail,
        "instance": str(request.url.path),
        "correlation_id": getattr(request.state, "correlation_id", None),
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Traduce excepciones de dominio a respuestas RFC 7807 (application/problem+json)."""

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            headers=exc.headers or None,
            content=problem_details(request, exc),
        )
