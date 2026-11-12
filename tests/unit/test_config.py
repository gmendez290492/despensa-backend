"""Pruebas unitarias de configuración."""

from pytest import MonkeyPatch

from app.core.config import Settings


def test_settings_defaults() -> None:
    """Verifica valores por defecto seguros en entorno local."""
    settings = Settings()
    assert settings.app_name == "Despensa API"
    assert settings.environment == "local"
    assert settings.smtp_port == 1025


def test_settings_reads_environment_variables(monkeypatch: MonkeyPatch) -> None:
    """Verifica que las variables de entorno sobrescriben la configuración."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings()
    assert settings.environment == "dev"
    assert settings.log_level == "DEBUG"
