"""Pruebas unitarias para las cabeceras de seguridad HTTP OWASP (Etapa 6)."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_security_headers_are_present_in_responses() -> None:
    """Verifica que el middleware inyecta cabeceras de endurecimiento recomendadas por OWASP."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/")

        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert "default-src 'none'" in response.headers["Content-Security-Policy"]
        assert "X-Correlation-ID" in response.headers
