# Orden Exacto de Estudio y Práctica (Paso a Paso)

Este documento es tu **índice maestro**. Sigue los pasos **en este orden exacto** para ir desde cero absoluto en Python y DevOps hasta dominar la Etapa 1 y estar listo para las siguientes etapas del proyecto Despensa.

> **Regla de oro:** no saltes al siguiente paso hasta haber ejecutado y entendido el paso actual en tu terminal. Todos los ejercicios corren gratis en tu PC con Docker.

---

## Paso 0: Encender tu Entorno de Práctica (`$0`)
- [ ] **0.1** Asegúrate de que **Rancher Desktop** esté abierto.
- [ ] **0.2** En PowerShell, dentro de la carpeta del proyecto, verifica que los contenedores estén arriba:
  ```powershell
  docker compose up -d
  docker compose ps
  ```
  *(Debes ver corriendo `postgres`, `rabbitmq`, `mailpit`, `api` y `worker`).*

---

## Fase 1: Aprender Python desde Cero y Practicar Lógica

### Paso 1: Familiarizarte con la sintaxis de Python
- [ ] **1.1** Lee completo [docs/python_desde_cero.md](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docs/python_desde_cero.md) (Secciones 1 a 10).
- [ ] **1.2** Prueba ejecutar el primer comando `print("Hola Python desde Docker")` en PowerShell para acostumbrarte a usar el contenedor `api`.

### Paso 2: Resolver la Etapa Básica de Ejercicios (`B1` a `B9`)
- [ ] **2.1** Abre [docs/ejercicios_fundamentos_3_niveles.md](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docs/ejercicios_fundamentos_3_niveles.md) → **Etapa 1 (Básica)**.
- [ ] **2.2** Resuelve y ejecuta uno por uno los ejercicios **`B1` al `B9`** (`Decimal`, strings, guard clauses, `for`/`while`/`zip`/`enumerate`, `any`/`all`).

### Paso 3: Resolver la Etapa Intermedia (`I1` a `I9`)
- [ ] **3.1** En el mismo archivo, pasa a la **Etapa 2 (Intermedia)**.
- [ ] **3.2** Resuelve **`I1` al `I9`** (`defaultdict`, `set`, trampa del argumento mutable, `sorted` + `lambda`, recursividad, excepciones personalizadas y POO con `@property`, `__repr__`, `__eq__`, polimorfismo).

### Paso 4: Resolver la Etapa Avanzada (`A1` a `A6`)
- [ ] **4.1** Pasa a la **Etapa 3 (Avanzada)**.
- [ ] **4.2** Resuelve **`A1` al `A6`** (scoring de recetas, FEFO atómico, Rate Limiter + backoff, caché TTL, mini-broker con DLQ e idempotencia, `asyncio.Semaphore` + `Lock`).

---

## Fase 2: Conectar Python con las Herramientas del Backend

### Paso 5: Practicar el Stack Real (`fundamentos_python_y_practica.md`)
- [ ] **5.1** Abre [docs/fundamentos_python_y_practica.md](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docs/fundamentos_python_y_practica.md).
- [ ] **5.2** Ejecuta y resuelve en orden los módulos:
  - **Módulo 1B y 1C** (POO del proyecto y fechas UTC/`ZoneInfo`).
  - **Módulo 2** (`type hints` y `mypy`).
  - **Módulo 3** (`async/await` y `asyncio.gather`).
  - **Módulo 4** (`Protocol` — Puertos y Adaptadores).
  - **Módulo 5** (`Pydantic v2` con `UserRegisterRequest`).
  - **Módulo 6** (`FastAPI` + `Depends` + `dependency_overrides`).
  - **Módulo 7** (`SQLAlchemy Async` + `commit`/`rollback` en `despensa_test`).
  - **Módulo 8** (`RabbitMQ` con `aio_pika`).
  - **Módulo 9** (`Pytest`: unitarios vs integración).

---

## Fase 3: Entender DevOps desde Cero

### Paso 6: Disección de Archivos y Ejercicios DevOps
- [ ] **6.1** Lee [docs/guia_devops_desde_cero.md](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docs/guia_devops_desde_cero.md) de principio a fin teniendo abiertos a un lado: [Dockerfile](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/Dockerfile), [docker-compose.yml](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docker-compose.yml) y [.github/workflows/ci.yml](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/.github/workflows/ci.yml).
- [ ] **6.2** Ejecuta en tu terminal los **5 ejercicios (`D1` a `D5`)**: tamaño e usuario no-root de `prod`, DNS interno de Docker, simulación del CI completo en local, `git diff`, y persistencia de volúmenes.

---

## Fase 4: Dominar la Etapa 1 y Cerrar el Primer Pull Request

### Paso 7: Recorrer la Arquitectura Real de Etapa 1
- [ ] **7.1** Lee [docs/guia_arquitectura_etapa1.md](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docs/guia_arquitectura_etapa1.md).
- [ ] **7.2** Haz los **6 ejercicios en vivo**:
  1. Registro en Swagger (`http://localhost:8000/docs`) + revisar `Mailpit` (`http://localhost:8025`) + `correlation_id` en logs.
  2. Inspeccionar tablas `users`, `outbox_events` y `processed_events` en `postgres`.
  3. Apagar `worker` (`docker compose stop worker`), registrar usuario y encenderlo para ver que el Outbox no pierde eventos.
  4. Probar seguridad JWT (Access vs Refresh y detección de reuso).
  5. Inspeccionar `despensa.events`, `notifications.user_registered` y `.dlq` en RabbitMQ (`http://localhost:15672`).
  6. Romper y arreglar un test unitario con `pytest`.
- [ ] **7.3** Responde las **9 preguntas de autoevaluación** al final de `guia_arquitectura_etapa1.md`.

### Paso 8: Revisar tu Código, Commitear y Abrir PR (Gitflow)
- [ ] **8.1** Revisa tus cambios locales con `git status` y `git diff`.
- [ ] **8.2** Corre la batería completa local (`ruff`, `mypy`, `bandit`, `pip-audit`, `pytest`).
- [ ] **8.3** Haz tu `commit` en `feature/etapa-1-users-outbox`, haz `git push -u origin feature/etapa-1-users-outbox` y abre el **Pull Request hacia `develop`** en GitHub verificando que los 4 jobs de CI queden en verde antes de hacer merge.

---

## Fase 5: Base de Datos Avanzada (Antes de Empezar Etapa 2)

### Paso 9: Profundizar en PostgreSQL y Caché
- [ ] **9.1** Lee [docs/guia_bd_avanzada_y_cache.md](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docs/guia_bd_avanzada_y_cache.md).
- [ ] **9.2** Ejecuta los **6 ejercicios SQL (`BD1` a `BD6`)** en `despensa_test`: `EXPLAIN ANALYZE`, índices parciales y `GIN`, `VIEW`, `Trigger` de `updated_at`, `Stored Procedure` de limpieza y `FOR UPDATE SKIP LOCKED`.
- [ ] **9.3** **Hito:** ya estás listo para retomar y construir la **Etapa 2 (`pantry`: lotes FEFO, `Idempotency-Key`, tests IDOR)** y luego **Etapas 3 y 4 (Alertas, Recetas, Redis Caché y Performance con Locust)**.

---

## Fase 6: Cloud e IaC (Antes de Empezar Etapa 5)

### Paso 10: Terraform, LocalStack y AWS
- [ ] **10.1** Una vez terminadas las Etapas 2, 3 y 4 en local, crearemos la guía práctica de **Terraform + LocalStack + AWS (VPC, ECS Fargate, RDS, SNS/SQS, OIDC y Budgets)** para practicar gratis antes de desplegar la **Etapa 5 y 6**.
