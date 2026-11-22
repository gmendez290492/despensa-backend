"""Middlewares transversales de la aplicación (trazabilidad por correlation_id)."""

from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Asigna y propaga un X-Correlation-ID único por cada petición HTTP."""

    header_name = "X-Correlation-ID"

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        incoming = request.headers.get(self.header_name)
        correlation_id = incoming.strip() if incoming and len(incoming.strip()) <= 64 else ""
        if not correlation_id:
            correlation_id = str(uuid4())

        request.state.correlation_id = correlation_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        try:
            response = await call_next(request)
            response.headers[self.header_name] = correlation_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()
