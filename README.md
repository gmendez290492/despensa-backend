# Despensa Backend — Etapa 1

Backend orientado a eventos construido en **Python (FastAPI)**, **PostgreSQL**, **Alembic**, **RabbitMQ**, **Mailpit** y **Docker Compose**, siguiendo flujo **Gitflow** y controles de calidad/seguridad en cada **Pull Request**.

## Qué incluye hasta la Etapa 1

- **Etapa 0:** FastAPI (`/health/live`, `/health/ready`), `structlog`, Docker multi-stage (usuario no-root en `prod`), CI con Ruff, Mypy, Bandit, `pip-audit`, Gitleaks y Trivy.
- **Etapa 1 (Módulo `users` + EDA):**
  - `POST /api/v1/auth/register` — registro con hashing **Argon2id**, validación de zona horaria IANA y evento `user.registered.v1` guardado en `outbox_events` en la misma transacción ACID.
  - `POST /api/v1/auth/login` — abre una **sesión** y emite Access Token (JWT corto con claim `sid`) y Refresh Token, con *rate limiting* por IP y por email.
  - `POST /api/v1/auth/refresh` — rotación de Refresh Tokens con detección de reuso (revoca la sesión afectada) y ventana de gracia opcional.
  - `POST /api/v1/auth/logout` — revoca la sesión: el Refresh **y los Access Tokens** de esa sesión dejan de ser válidos.
  - `POST /api/v1/auth/password/forgot` y `POST /api/v1/auth/password/reset` — recuperación de contraseña por correo (token de un solo uso, 30 min).
  - `GET /api/v1/users/me` — endpoint protegido con JWT Bearer (valida que la sesión siga activa).
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

Alertas de caducidad automáticas (scheduler, opt-in). Sin él, solo se generan con `POST /api/v1/notifications/scan`:
```powershell
docker compose --profile scheduler up -d scheduler
# Para probar sin esperar una hora: $env:EXPIRATION_SCAN_INTERVAL_SECONDS=60 antes del comando
```

**Límites en local:** sin proxy delante de Next.js, todos los usuarios y pestañas llegan a FastAPI con la misma IP y comparten cada rate limit (p. ej. 5 registros por hora en total). Para probar con varias cuentas, copia `.env.example` a `.env`, descomenta el bloque "Pruebas locales / E2E" y ejecuta `docker compose up -d api`.

Ejecutar suite completa de calidad, seguridad y pruebas:
```powershell
docker compose exec -T api ruff check .
docker compose exec -T api ruff format --check .
docker compose exec -T api mypy src
docker compose exec -T api bandit -c pyproject.toml -r src
docker compose exec -T api pip-audit
docker compose exec -T api pytest -v
```

## Seguridad de autenticación (issue #9)

| Tema | Comportamiento |
| --- | --- |
| Logout | Revoca la sesión (`auth_sessions`). Cualquier access token con ese `sid` recibe `401 invalid-token` de inmediato. |
| Reuso de refresh | Un refresh ya rotado revoca **solo su sesión** (las demás sesiones del usuario siguen activas). |
| Ventana de gracia | Si el login envió `X-Client-Binding`, ese valor se exige en cada refresh y, durante `REFRESH_REUSE_GRACE_SECONDS` (10 s), el refresh anterior devuelve **el mismo par sucesor** en lugar de revocar. Sin binding no hay gracia. |
| Registro duplicado | Se mantiene `409 email-already-exists` (riesgo aceptado de enumeración), mitigado con límite estricto por IP (`REGISTER_RATE_LIMIT_*`) y por email (`AUTH_EMAIL_RATE_LIMIT_*`). |
| Login | Tiempo de respuesta igualado para correos inexistentes (verificación Argon2 contra un hash de referencia). |
| Rate limiting | Backend `postgres` (tabla `rate_limit_buckets`), compartido entre réplicas y persistente entre deploys. Los `429` incluyen `Retry-After`. Las claves por email se guardan como SHA-256. `refresh` y `logout` limitan por IP y ruta (`REFRESH_RATE_LIMIT_*`, 30/min por defecto). |
| IP del cliente | Uvicorn usa `X-Forwarded-For` solo si el emisor está en `FORWARDED_ALLOW_IPS`. En AWS es el CIDR de la VPC (el SG de ECS solo admite tráfico del ALB). **Nunca** usar `*` fuera de local. |
| Recuperación | `forgot` responde `202` siempre. El worker genera el token (no viaja por Outbox ni broker), guarda solo su hash y envía el enlace `${FRONTEND_BASE_URL}/reset-password?token=...`. El reset revoca todas las sesiones. |

**E2E del frontend:** la suite supera los límites por defecto. Relájalos solo en ese entorno, por ejemplo:

```powershell
$env:AUTH_RATE_LIMIT_MAX_ATTEMPTS=1000; $env:REGISTER_RATE_LIMIT_MAX_ATTEMPTS=1000; $env:AUTH_EMAIL_RATE_LIMIT_MAX_ATTEMPTS=1000; $env:REFRESH_RATE_LIMIT_MAX_ATTEMPTS=1000
docker compose up -d api
```

## Worker en AWS

En AWS el worker corre como **contenedor sidecar** dentro de la misma tarea Fargate que la API: comparten CPU y memoria, y así no se paga una segunda tarea. Los backends se eligen por entorno:

| Variable | Local (compose) | AWS (ECS) |
|---|---|---|
| `MESSAGING_BACKEND` | `rabbitmq` | `aws`: el Outbox publica en SNS y el worker consume la cola SQS de notificaciones |
| `EMAIL_BACKEND` | `smtp` (Mailpit) | `ses` |
| `SNS_TOPIC_ARN`, `SQS_NOTIFICATIONS_QUEUE_URL` | — | Obligatorias con `MESSAGING_BACKEND=aws` |

- La suscripción SNS → SQS usa `raw_message_delivery`, así que el cuerpo es el `EventEnvelope` tal cual. El consumidor también acepta el sobre de SNS por si se desactiva.
- Un mensaje solo se borra si su handler termina bien. Si falla, SQS lo reentrega tras el *visibility timeout* y, a las 3 recepciones, lo mueve a la DLQ. Los eventos sin handler se confirman y se ignoran.
- El contenedor `worker` no es esencial: si cae, la API sigue sirviendo y ECS lo reinicia (`restartPolicy`).
- En ECS no se pasan credenciales: boto3 usa el rol de la tarea, con permisos mínimos sobre la cola y la identidad SES.
- **SES:** `ses_from_email` (en `terraform.tfvars`) se crea como identidad y AWS envía un correo de verificación a esa dirección. Mientras la cuenta siga en el *sandbox* de SES, los destinatarios también tienen que estar verificados.
- El emulador de AWS del compose no reparte de SNS a SQS, así que en local el flujo completo se prueba con RabbitMQ.

## Idempotencia de mutaciones (issue #11)

Las mutaciones de pantry aceptan la cabecera opcional `Idempotency-Key` (`^[A-Za-z0-9_-]{8,128}$`): `POST /pantries`, `/pantries/join`, `/pantries/{id}/locations`, `/products`, `/pantries/{id}/batches` y `/pantries/{id}/consume`. La outbox offline del frontend envía su `clientMutationId` en esa cabecera.

| Caso | Respuesta |
|---|---|
| Sin cabecera | Comportamiento de siempre. |
| Clave nueva | Se ejecuta. El efecto y la respuesta guardada se confirman en el mismo commit. |
| Misma clave y misma petición (método, ruta y cuerpo) | Se repite la respuesta guardada, con el mismo status y cuerpo, sin ejecutar nada. Lleva `Idempotent-Replayed: true`. |
| Misma clave y otra petición | `422 idempotency-key-reused`. |
| Otra petición con la clave en curso | Espera a que termine y repite su respuesta. Si espera más de `IDEMPOTENCY_LOCK_TIMEOUT_MS` (5 s), `409 idempotency-request-in-progress` con `Retry-After`. |
| Error de negocio 4xx (p. ej. `insufficient-stock`) | Se guarda y se repite igual, aunque el estado cambie después. |
| Error 5xx | No se guarda: la clave queda libre para reintentar. |
| Formato inválido | `400 invalid-idempotency-key`. |

- Las claves pertenecen al usuario (`idempotency_keys`, PK `(user_id, key)`): la misma clave de otro usuario no colisiona ni expone su respuesta.
- Caducan a las `IDEMPOTENCY_KEY_TTL_HOURS` (168 h = 7 días). Una clave caducada se trata como nueva, así que **la outbox del frontend no debe reenviar operaciones más antiguas que el TTL**. Las caducadas se purgan de forma oportunista, sin depender del scheduler.

## URLs útiles en local

- **Swagger UI (API):** http://localhost:8000/docs
- **Health Readiness:** http://localhost:8000/health/ready
- **RabbitMQ Management UI:** http://localhost:15672 (`despensa` / `despensa_dev_pass`)
- **Mailpit UI (correos locales):** http://localhost:8025
