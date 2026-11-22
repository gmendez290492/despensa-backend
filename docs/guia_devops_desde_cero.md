# Guía DevOps desde Cero (Explicación Archivo por Archivo y Ejercicios)

Esta guía está pensada para quien **nunca ha trabajado con DevOps**. Explicaremos qué problema resuelve cada archivo de configuración de tu proyecto, línea por línea, y tendrás ejercicios para comprobarlo en tu máquina.

---

## 1. ¿Qué es el Ciclo DevOps (y DevSecOps)?

Sin DevOps, el ciclo clásico es: *"En mi compu sí funcionaba"*, subir contraseñas por accidente, desplegar a mano copiando archivos y rezar para que nada se rompa.

Con **DevOps + DevSecOps**, automatizamos 4 etapas continuas:
1. **Control de versiones (Git + Gitflow):** nadie edita producción directo; todo cambio viaja en ramas y se revisa en un **Pull Request (PR)**.
2. **Empaquetado reproducible (Docker):** tu app corre en la misma "caja" Linux en tu PC Windows, en GitHub Actions y en AWS.
3. **Integración Continua (CI):** cada vez que abres un PR, un servidor limpio corre linters, tipado, escaneos de seguridad y pruebas automáticas.
4. **Infraestructura como Código (IaC) y Despliegue Continuo (CD):** los servidores y bases de datos en AWS se definen en archivos `.tf` (Terraform) y se despliegan automáticamente al aprobar cambios.

---

## 2. Git, Gitflow y Protección de Secretos

### Cómo funciona Gitflow en este proyecto
- **`main`:** código estable listo para producción. **Nunca** se programa directo aquí.
- **`develop`:** rama de integración donde se juntan todas las etapas terminadas.
- **`feature/<nombre>`:** rama temporal para una sola funcionalidad (hoy estás en `feature/etapa-1-users-outbox`). Al terminar, abres un **PR hacia `develop`**.
- **`release/*` y `hotfix/*`:** ramas para preparar salidas a producción o parches urgentes sobre `main`.

### Qué protegen [`.gitignore`](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/.gitignore) y [`.env.example`](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/.env.example)
- **`.gitignore`** le dice a Git qué **NO** debe rastrear jamás:
  - `.env` y `.env.*` (ahí vivirán tus claves reales).
  - `__pycache__/`, `.venv/`, `.pytest_cache/` (archivos temporales generados en tu PC).
  - `*.tfstate`, `*.tfvars` (archivos de Terraform que pueden contener datos sensibles).
- **`!.env.example`** (el `!` significa excepción): sí se sube a Git como plantilla con valores falsos/de ejemplo para que cualquier desarrollador sepa qué variables necesita la app.

---

## 3. Docker Explicado Línea por Línea

### ¿Imagen vs Contenedor?
- **Imagen:** es como el **plano o molde** de una máquina virtual ligera (ej. *Python 3.12 + nuestras librerías*). Es de solo lectura.
- **Contenedor:** es una **instancia viva** creada a partir de una imagen (ej. `despensa-api`). Puedes encenderlo, apagarlo o destruirlo; si quieres conservar datos (como tu BD), usas **volúmenes**.

### Disección de nuestro [`Dockerfile`](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/Dockerfile)

Nuestro `Dockerfile` usa **Multi-Stage Build** (construcción en múltiples etapas) para tener lo mejor de dos mundos: herramientas de prueba en desarrollo e imagen mínima y segura en producción.

1. **Etapa `builder` (`FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder`):**
   - `WORKDIR /app`: crea y entra a la carpeta `/app` dentro del contenedor.
   - `COPY pyproject.toml README.md ./` seguido de `RUN uv sync --no-install-project --no-dev`:
     - **Truco clave de caché Docker:** copiamos primero solo `pyproject.toml` antes de copiar `src/`. Así, si solo editas código Python en `src/`, Docker **reutiliza la capa de librerías ya descargadas** y reconstruye en 2 segundos en lugar de bajar todo de internet otra vez.
   - `COPY src ./src` y `RUN uv sync --no-dev --no-editable`: instala nuestra app dentro de `/app/.venv`.
2. **Etapa `dev` (`AS dev`):**
   - Instala también las dependencias de desarrollo (`pytest`, `ruff`, `mypy`, `bandit`, `pip-audit`) para que puedas correr todas las pruebas dentro del contenedor sin instalar Python en Windows.
   - Usa `--reload` para reiniciar Uvicorn cada vez que guardas un archivo.
3. **Etapa `prod` (`FROM python:3.12-slim-bookworm AS prod`):**
   - Empieza desde una imagen limpia sin `uv` ni `pytest` (ocupa menos espacio y tiene menos superficie de ataque).
   - `RUN groupadd ... && useradd ... appuser` + `USER appuser`: **regla de oro de seguridad en contenedores**. Nunca correr la app como `root` en producción; si alguien vulnera la API, no tendrá permisos de administrador del contenedor.
   - `COPY --from=builder`: copia **solo** `.venv`, `src`, `alembic.ini` y `migrations`.
   - `HEALTHCHECK`: le enseña a Docker/AWS a preguntar cada 30s a `/health/live` si el proceso sigue sano.

### Qué hace [`.dockerignore`](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/.dockerignore)
Evita copiar `.git`, `.venv`, `tests` o `docs` al contexto de construcción de Docker, haciendo el build rápido y evitando filtrar archivos locales dentro de la imagen.

---

## 4. Docker Compose Explicado Sección por Sección

[`docker-compose.yml`](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docker-compose.yml) orquesta **6 piezas** que colaboran entre sí dentro de una **red privada virtual**:

1. **Nombres de red internos (`postgres`, `rabbitmq`, `mailpit`):**
   - Dentro de Docker Compose, `api` **no** busca a PostgreSQL en `localhost:5432` (porque `localhost` dentro de `despensa-api` es el propio contenedor `api`), sino usando el nombre del servicio: `postgres:5432` o `rabbitmq:5672`.
   - `ports: - "8000:8000"` significa: *"conecta el puerto `8000` de tu Windows (`izquierda`) con el puerto `8000` del contenedor (`derecha`)"*.
2. **Volúmenes (`volumes:`):**
   - **Volúmenes nombrados** (`postgres_data:/var/lib/postgresql/data`): guardan los datos de PostgreSQL aunque apagues y borres los contenedores con `docker compose down`. *(Solo se borran si pasas `docker compose down -v`)*.
   - **Bind mounts** (`./src:/app/src`): conectan tu carpeta real de Windows dentro del contenedor en vivo para que al editar en VS Code el cambio se refleje al instante.
3. **Orden de arranque (`depends_on` + `condition`):**
   - `postgres` y `rabbitmq` tienen `healthcheck` (no basta con que el contenedor inicie; debe responder `pg_isready` o `rabbitmq-diagnostics ping`).
   - `migrate` espera a que `postgres` esté `service_healthy`, corre `alembic upgrade head` y termina (`restart: "no"`).
   - `api` y `worker` esperan a que `migrate` termine con éxito (`service_completed_successfully`) y a que `rabbitmq` esté sano.
4. **Sintaxis `${VAR:-valor_default}`:**
   - Toma el valor de tu archivo `.env` si existe; si no existe, usa `valor_default`.

---

## 5. Pipeline CI/DevSecOps Explicado ([`.github/workflows/ci.yml`](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/.github/workflows/ci.yml))

Cada vez que haces `push` o abres un PR hacia `main` o `develop`, GitHub levanta máquinas Linux temporales (`ubuntu-latest`) y corre **4 jobs en paralelo**:

1. **`quality-and-unit-tests`:**
   - `ruff check .` y `ruff format --check .`: estilo y errores comunes.
   - `mypy src`: valida tipos sin ejecutar código.
   - `bandit`: escaneo estático de seguridad (SAST) buscando patrones peligrosos.
   - `pip-audit`: revisa si alguna librería instalada tiene vulnerabilidades públicas (CVEs).
   - `pytest tests/unit --cov=app`: corre tests unitarios y reporta cobertura.
2. **`integration-tests`:**
   - Levanta un `postgres` y `rabbitmq` temporales dentro del runner de GitHub (`services:`).
   - Aplica `alembic upgrade head` desde cero (garantiza que tus migraciones no estén rotas).
   - Corre `pytest tests/integration` contra servicios reales.
3. **`secret-scan` (Gitleaks):**
   - Escanea el historial de Git para bloquear el PR si alguien subió una contraseña, token o llave AWS real.
4. **`container-security` (Docker + Trivy):**
   - Construye el `target: prod` del `Dockerfile`.
   - Corre **Trivy** sobre la imagen final y falla (`exit-code: "1"`) si encuentra vulnerabilidades `CRITICAL` o `HIGH` con parche disponible.
   - *Nota de seguridad:* fíjate que `trivy-action` está fijado por su **commit SHA** (`@ed142fd...`) en lugar de un tag mutable, protegiendo tu pipeline contra ataques de cadena de suministro (*supply-chain*).

---

## 6. Ejercicios Prácticos de DevOps (Para hacer en tu terminal)

### Ejercicio D1: Ver la diferencia de tamaño y seguridad entre imagen `dev` y `prod`
Ejecuta en PowerShell:
```powershell
docker images despnsaproject-api
docker images despensa-api
docker run --rm despensa-api:prod-check id
```
- **Qué debes observar:**
  1. Compara el tamaño (`SIZE`) de la imagen `dev` vs `prod-check`.
  2. El comando `id` en `prod-check` debe imprimir `uid=10001(appuser) gid=10001(appgroup)` (¡no `root`!).

### Ejercicio D2: Probar comunicación por red interna de Docker
Desde dentro del contenedor `api`, comprueba cómo resuelve los nombres `postgres` y `rabbitmq`:
```powershell
docker compose exec -T api python -c "import socket; print('postgres:', socket.gethostbyname('postgres'), 'rabbitmq:', socket.gethostbyname('rabbitmq'))"
```
- **Pregunta:** ¿Por qué da IPs internas tipo `172.x.x.x` en lugar de `127.0.0.1`?

### Ejercicio D3: Simular el pipeline CI completo en tu PC antes de subir a GitHub
Corre esta secuencia (es exactamente lo que corre GitHub Actions en cada PR, pero gratis y en segundos en tu PC):
```powershell
docker compose exec -T api ruff check .
docker compose exec -T api ruff format --check .
docker compose exec -T api mypy src
docker compose exec -T api bandit -c pyproject.toml -r src
docker compose exec -T api pip-audit
docker compose exec -T api pytest -v
```

### Ejercicio D4: Practicar inspección de Git antes de commitear
```powershell
git branch
git status
git diff .github/workflows/ci.yml
```
- **Objetivo:** acostumbrarte a leer tu propio `diff` antes de hacer `git add` y `git commit` (primer filtro de calidad de todo ingeniero).

### Ejercicio D5: Simular pérdida controlada y persistencia de volúmenes
1. Crea un usuario en Swagger (`http://localhost:8000/docs`).
2. Apaga y borra los contenedores (sin `-v`): `docker compose down`
3. Vuelve a levantarlos: `docker compose up -d`
4. Intenta hacer login en Swagger con ese mismo usuario: **sigue existiendo** porque vive en el volumen `postgres_data`.
*(Nota: solo si algún día quieres borrar toda tu BD local desde cero usarías `docker compose down -v`).*
