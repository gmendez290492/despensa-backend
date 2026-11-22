# Despensa Backend — Etapa 1

Backend orientado a eventos construido en **Python (FastAPI)**, **PostgreSQL**, **Alembic**, **RabbitMQ**, **Mailpit** y **Docker Compose**, siguiendo flujo **Gitflow** y controles de calidad/seguridad en cada **Pull Request**.

## Qué incluye hasta la Etapa 1

- **Etapa 0:** FastAPI (`/health/live`, `/health/ready`), `structlog`, Docker multi-stage (usuario no-root en `prod`), CI con Ruff, Mypy, Bandit, `pip-audit`, Gitleaks y Trivy.
- **Etapa 1 (Módulo `users` + EDA):**
  - `POST /api/v1/auth/register` — registro con hashing **Argon2id**, validación de zona horaria IANA y evento `user.registered.v1` guardado en `outbox_events` en la misma transacción ACID.
  - `POST /api/v1/auth/login` — emisión de Access Token (JWT corto) y Refresh Token con *rate limiting*.
  - `POST /api/v1/auth/refresh` — rotación de Refresh Tokens con detección de reuso.
  - `POST /api/v1/auth/logout` — revocación de Refresh Token.
  - `GET /api/v1/users/me` — endpoint protegido con JWT Bearer.
  - **Worker (`src/app/worker.py`):** lee el Outbox (`FOR UPDATE SKIP LOCKED`), publica en RabbitMQ (`despensa.events` + DLQ) y procesa de forma idempotente el correo de bienvenida en **Mailpit**.
  - **Migraciones (`alembic`):** servicio `migrate` ejecuta `alembic upgrade head` antes de iniciar API y Worker.

## Comandos rápidos en local (con Docker)

Levantar todo el stack (incluye migraciones, API y Worker):
```powershell
docker compose up -d --build
```

Ver logs de API y Worker:
```powershell
docker compose logs -f api worker
```

Ejecutar suite completa de calidad, seguridad y pruebas:
```powershell
docker compose exec -T api ruff check .
docker compose exec -T api ruff format --check .
docker compose exec -T api mypy src
docker compose exec -T api bandit -c pyproject.toml -r src
docker compose exec -T api pip-audit
docker compose exec -T api pytest -v
```

## URLs útiles en local

- **Swagger UI (API):** http://localhost:8000/docs
- **Health Readiness:** http://localhost:8000/health/ready
- **RabbitMQ Management UI:** http://localhost:15672 (`despensa` / `despensa_dev_pass`)
- **Mailpit UI (correos locales):** http://localhost:8025
