# Despensa Backend — Etapa 0

Backend orientado a eventos construido en **Python (FastAPI)**, **PostgreSQL**, **RabbitMQ** y **Docker Compose**, con pipeline **CI/DevSecOps** en GitHub Actions.

## Qué incluye la Etapa 0

- `src/app/main.py`: aplicación FastAPI con ciclo de vida (`lifespan`) y endpoints:
  - `GET /` — metadata del servicio.
  - `GET /health/live` — liveness probe (el proceso responde).
  - `GET /health/ready` — readiness probe (verifica conectividad real con PostgreSQL y RabbitMQ).
- `src/app/core/`: configuración tipada (`config.py`), logging estructurado (`logging.py`), motor async SQLAlchemy (`database.py`) y chequeos de salud (`health.py`).
- `Dockerfile`: construcción multi-stage (`dev` para trabajar con herramientas de calidad y `prod` con imagen ligera sin usuario `root`).
- `docker-compose.yml`: levanta `api`, `postgres`, `rabbitmq` y `mailpit` en tu PC (`$0`).
- `.github/workflows/ci.yml`: ejecuta Ruff, Mypy, Bandit, `pip-audit`, Pytest, Gitleaks y escaneo de imagen con Trivy.

## Comandos rápidos en local (con Docker)

Levantar todo el stack:
```powershell
docker compose up -d --build
```

Ver logs de la API:
```powershell
docker compose logs -f api
```

Ejecutar pruebas, linter, tipado y seguridad dentro del contenedor:
```powershell
docker compose exec api pytest -v
docker compose exec api ruff check .
docker compose exec api ruff format --check .
docker compose exec api mypy src
docker compose exec api bandit -c pyproject.toml -r src
```

Apagar el stack (conservando datos en volúmenes):
```powershell
docker compose down
```

## URLs útiles en local

- **Swagger UI (API):** http://localhost:8000/docs
- **Health Readiness:** http://localhost:8000/health/ready
- **RabbitMQ Management UI:** http://localhost:15672 (usuario/clave por defecto: `despensa` / `despensa_dev_pass`)
- **Mailpit (correos locales):** http://localhost:8025
