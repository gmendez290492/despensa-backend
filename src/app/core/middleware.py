"""Middlewares transversales de la aplicación (trazabilidad y cabeceras de seguridad).

Son middlewares ASGI puros y no `BaseHTTPMiddleware`: este último envuelve cada petición en
una tarea y streams de memoria adicionales, y en el perfil de carga del issue #16 era una
parte visible del coste por petición.
"""

from uuid import uuid4

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_DOCS_PATHS = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})
_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'"
)
_DEFAULT_CSP = "default-src 'none'; frame-ancestors 'none'"


class CorrelationIdMiddleware:
    """Asigna y propaga un X-Correlation-ID único por cada petición HTTP."""

    header_name = "X-Correlation-ID"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(self.header_name)
        correlation_id = incoming.strip() if incoming and len(incoming.strip()) <= 64 else ""
        if not correlation_id:
            correlation_id = str(uuid4())

        # request.state lee de scope["state"]
        scope.setdefault("state", {})["correlation_id"] = correlation_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[self.header_name] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            structlog.contextvars.clear_contextvars()


class SecurityHeadersMiddleware:
    """Inyecta cabeceras HTTP de seguridad recomendadas por OWASP para mitigar ataques web."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_docs = scope["path"] in _DOCS_PATHS

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["X-XSS-Protection"] = "1; mode=block"
                if is_docs:
                    headers["Content-Security-Policy"] = _DOCS_CSP
                elif "Content-Security-Policy" not in headers:
                    headers["Content-Security-Policy"] = _DEFAULT_CSP
            await send(message)

        await self.app(scope, receive, send_with_headers)
