# Documentación, Ejemplos y Ejercicios: Fundamentos de Python y el Stack Backend

Esta guía forma parte de [ruta_aprendizaje_practica.md](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docs/ruta_aprendizaje_practica.md) y complementa a [guia_arquitectura_etapa1.md](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docs/guia_arquitectura_etapa1.md). Aquí aprenderás **desde cero** (fundamentos de programación, POO, Python y herramientas del stack) mediante **ejemplos cortos ejecutables** y **ejercicios prácticos** que corren directamente dentro de tu contenedor Docker `despensa-api`.

> **Cómo ejecutar cualquier ejemplo en PowerShell:**  
> Copia el bloque `@' ... '@ | docker compose exec -T api python -` y pégalo en tu terminal dentro de la carpeta del proyecto. (El contenedor `api` debe estar encendido con `docker compose up -d`).

---

## Documentación Oficial de Referencia

Cuando quieras profundizar en alguna librería del proyecto, consulta su fuente oficial:
- **Python 3.12 (Tutorial oficial):** https://docs.python.org/es/3.12/tutorial/
- **FastAPI (Guía de usuario):** https://fastapi.tiangolo.com/es/tutorial/
- **Pydantic v2 (Modelos y validadores):** https://docs.pydantic.dev/latest/
- **SQLAlchemy 2.0 (Tutorial unificado async):** https://docs.sqlalchemy.org/en/20/tutorial/
- **Alembic (Migraciones):** https://alembic.sqlalchemy.org/en/latest/tutorial.html
- **RabbitMQ (Tutoriales AMQP):** https://www.rabbitmq.com/tutorials
- **Pytest (Testing):** https://docs.pytest.org/en/stable/
- **Ruff (Linter/Formatter) y uv:** https://docs.astral.sh/
- **Mypy (Tipado estático):** https://mypy.readthedocs.io/

---

## Módulo 0: Repaso de Fundamentos de Programación (Lógica Base)

Antes de entrar a FastAPI o bases de datos, asegúrate de dominar estas 5 ideas que usarás en la lógica de despensa y recetas:

1. **Inmutabilidad vs Mutabilidad:**
   - Una `list` o `dict` se puede modificar en sitio (*mutable*); una `tuple` o `str` o `@dataclass(frozen=True)` no cambia (*inmutable*, evita efectos secundarios inesperados).
2. **Funciones puras vs Efectos secundarios (*Side Effects*):**
   - Una **función pura** (ej. calcular el puntaje de una receta según ingredientes por vencer) siempre devuelve lo mismo para las mismas entradas y **no** toca BD ni red. Eso la vuelve facilísima de testear con `pytest`.
3. **Estructuras de datos según el problema:**
   - `list` → mantener orden (ej. ordenar lotes por fecha de caducidad **FEFO**).
   - `set` → intersecciones rápidas (ej. *¿qué ingredientes de la receta ya tengo en mi despensa?*: `disponibles & requeridos`).
   - `dict` → búsqueda instantánea por clave `O(1)` (ej. mapa `{ingrediente_id: cantidad_disponible}`).
4. **Ordenamiento con clave (`sorted(..., key=...)`):** indispensable para ordenar alimentos del que caduca primero al último.
5. **Excepciones como flujo de control limpio:** en lugar de devolver códigos mágicos `-1`, lanzamos excepciones específicas (`raise ValueError(...)` o `DomainError`) y las capturamos en un solo lugar.

### Ejemplo ejecutable (lógica de despensa FEFO y matching de recetas)
```powershell
@'
# 1. Ordenar lotes por caducidad (FEFO: First Expired, First Out)
lotes_leche = [
    {"lote": "L2", "vence_en_dias": 7, "litros": 1.0},
    {"lote": "L1", "vence_en_dias": 2, "litros": 0.5},
    {"lote": "L3", "vence_en_dias": 12, "litros": 2.0},
]
ordenados = sorted(lotes_leche, key=lambda x: x["vence_en_dias"])
print("Orden FEFO:", [item["lote"] for item in ordenados])

# 2. Conjuntos (set) para saber qué te falta para una receta
tengo = {"huevo", "leche", "sal", "tomate"}
receta_omelette = {"huevo", "queso", "sal"}
print("Ya tengo:", tengo & receta_omelette)
print("Me falta:", receta_omelette - tengo)
'@ | docker compose exec -T api python -
```

### Ejercicio 0
Escribe y ejecuta un bloque en Python que:
1. Tenga una lista de 4 lotes de inventario con `{"producto": ..., "cantidad": ..., "dias": ...}`.
2. Implemente una función pura `consumir_fefo(lotes, cantidad_a_usar)` que descuente empezando por los lotes con menor `dias`, y lance `ValueError("Stock insuficiente")` si la suma total no alcanza.

---

## Módulo 1: Sintaxis Esencial de Python

### Conceptos clave
1. **Indentación en lugar de llaves `{}`:** Python usa 4 espacios para definir bloques (`if`, `def`, `class`).
2. **Colecciones principales:**
   - `list`: lista ordenada y mutable (`["leche", "huevo"]`).
   - `dict`: diccionario clave-valor (`{"nombre": "Leche", "dias": 3}`).
   - `set`: conjunto sin duplicados (`{"lacteos", "frutas"}`).
3. **Funciones y parámetros por nombre (`*`):** cuando ves `def crear(*, email: str, activo: bool = True)`, el `*` obliga a pasar `email=...` por nombre, evitando confundir el orden de los argumentos.
4. **Context Managers (`with` / `async with`):** garantizan cerrar un archivo, conexión o sesión de BD automáticamente al salir del bloque, incluso si ocurre un error.
5. **`try / except / finally`:** captura errores (`except`) y ejecuta limpieza obligatoria (`finally`).

### Ejemplo ejecutable
```powershell
@'
from dataclasses import dataclass

@dataclass
class Producto:
    nombre: str
    dias_para_caducar: int

despensa = [
    Producto(nombre="Leche", dias_para_caducar=2),
    Producto(nombre="Arroz", dias_para_caducar=180),
    Producto(nombre="Yogurt", dias_para_caducar=1),
]

por_vencer = [p.nombre for p in despensa if p.dias_para_caducar <= 3]
print(f"Productos urgentes: {por_vencer}")
'@ | docker compose exec -T api python -
```

### Ejercicio 1
Modifica el bloque anterior y ejecútalo para que:
1. Agregues un cuarto producto (`"Pan"`, `dias_para_caducar=3`).
2. En lugar de imprimir solo los nombres, imprimas un diccionario `{nombre: dias}` únicamente de los productos con `dias_para_caducar <= 3` (pista: `{p.nombre: p.dias_para_caducar for p in despensa if ...}`).

---

## Módulo 1B: Programación Orientada a Objetos (POO) y SOLID en Python

### Conceptos clave de POO en nuestro Backend
1. **Clase, Objeto, `__init__` y `self`:**
   - Una `class` es el molde (ej. `UserService`), un objeto es la instancia creada (`service = UserService(session, settings)`), y `self` es la referencia a esa instancia (como `this` en Java/JS/C#).
2. **Encapsulación y `@property`:**
   - Por convención en Python, un atributo o método que empieza con `_` (ej. `_exchange` o `_issue_tokens`) es **interno/privado** de la clase.
   - `@property` te permite exponer un cálculo como si fuera un atributo de solo lectura (`lote.esta_vencido`) validando reglas internas.
3. **Composición sobre Herencia:**
   - En lugar de crear árboles profundos de herencia (`BaseService -> AuthBaseService -> UserService`), inyectamos colaboradores dentro de `__init__` (`self.users = UserRepository(session)` y `self.outbox = OutboxRepository(session)`).
4. **SOLID aplicado a nuestro proyecto:**
   - **S (Single Responsibility):** `router.py` solo maneja HTTP; `repository.py` solo SQL; `service.py` solo negocio.
   - **O / D (Open-Closed & Dependency Inversion):** `WelcomeEmailHandler` depende de la abstracción `EmailSender`, no de Mailpit ni de Amazon SES.

### Ejemplo ejecutable (POO: encapsulación, `@property` y composición)
```powershell
@'
from datetime import date, timedelta

class LoteDespensa:
    def __init__(self, nombre: str, cantidad: float, vence_el: date) -> None:
        if cantidad < 0:
            raise ValueError("La cantidad inicial no puede ser negativa")
        self.nombre = nombre
        self._cantidad = cantidad
        self.vence_el = vence_el

    @property
    def cantidad(self) -> float:
        return self._cantidad

    @property
    def esta_vencido(self) -> bool:
        return date.today() > self.vence_el

    def consumir(self, monto: float) -> None:
        if monto <= 0:
            raise ValueError("El consumo debe ser positivo")
        if monto > self._cantidad:
            raise ValueError(f"Stock insuficiente de {self.nombre}")
        self._cantidad -= monto

leche = LoteDespensa("Leche", 2.0, date.today() + timedelta(days=2))
leche.consumir(0.5)
print(f"{leche.nombre}: quedan {leche.cantidad}L | vencido={leche.esta_vencido}")
'@ | docker compose exec -T api python -
```

### Ejercicio 1B
1. Extiende `LoteDespensa` agregando una `@property` llamada `dias_restantes` que retorne `(self.vence_el - date.today()).days`.
2. Prueba intentar consumir `5.0` litros y verifica que lanza `ValueError`.
3. Abre [src/app/modules/users/service.py](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/src/app/modules/users/service.py) y observa cómo `UserService.__init__` aplica **composición** guardando `self.users` y `self.outbox`.

---

## Módulo 1C: Conceptos Indispensables del Proyecto (UTC, HTTP e Idempotencia)

1. **Fechas siempre en UTC (`datetime.now(UTC)`) + `ZoneInfo`:**
   - Los servidores en AWS corren en UTC. Nunca guardes fechas locales sin zona horaria (*naive datetimes*). Guardamos todo en UTC y solo convertimos a `ZoneInfo(user.timezone)` cuando calculamos a qué hora local avisar al usuario.
2. **Códigos HTTP correctos en APIs REST:**
   - `200 OK` (consulta/login), `201 Created` (recurso creado), `204 No Content` (logout/borrado), `401 Unauthorized` (sin token o inválido), `403 Forbidden` (autenticado pero sin permiso), `409 Conflict` (email duplicado), `422 Unprocessable Entity` (JSON inválido), `429 Too Many Requests` (rate limit), `503 Service Unavailable` (BD o RabbitMQ caído).
3. **Serialización JSON (`UUID` y fechas ISO-8601):**
   - JSON nativo no entiende objetos `UUID` ni `datetime`; por eso en Pydantic usamos `.model_dump(mode="json")` o `.model_dump_json()` al guardar en `outbox_events` o enviar a RabbitMQ.

### Ejemplo ejecutable (UTC vs Zona Horaria del Usuario)
```powershell
@'
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

ahora_utc = datetime.now(UTC)
cdmx = ahora_utc.astimezone(ZoneInfo("America/Mexico_City"))
madrid = ahora_utc.astimezone(ZoneInfo("Europe/Madrid"))

print("UTC:   ", ahora_utc.isoformat())
print("CDMX:  ", cdmx.isoformat())
print("Madrid:", madrid.isoformat())
'@ | docker compose exec -T api python -
```

### Ejercicio 1C
Ejecuta el bloque anterior cambiando `"America/Mexico_City"` por tu zona horaria (o `"America/Bogota"`, `"America/Buenos_Aires"`) y comprueba que los tres instantes representan exactamente el mismo momento en el tiempo pero con distinto *offset*.

---

## Módulo 2: Tipado Estático (`type hints`) y `mypy`

### Conceptos clave
En Python los tipos se anotan así:
- Variables y parámetros: `edad: int = 25`, `email: str`
- Retorno de función: `def saludar(nombre: str) -> str:` (o `-> None` si no retorna nada)
- Valores opcionales: `User | None` significa "un `User` o `None`".

`mypy` analiza el código **antes de ejecutarlo** para detectar errores como intentar acceder a `user.email` sin verificar antes `if user is None:`.

### Ejemplo ejecutable (detectando un bug con `mypy`)
```powershell
@'
def obtener_dominio(email: str | None) -> str:
    # Si descomentas la línea siguiente sin validar None, mypy marcará error:
    # return email.split("@")[1]
    if email is None:
        return "sin-correo"
    return email.split("@")[1]

print(obtener_dominio("ana@despensa.local"))
print(obtener_dominio(None))
'@ | docker compose exec -T api python -
```

### Ejercicio 2
1. Corre `docker compose exec -T api mypy src` y observa que reporta 0 errores en los archivos del proyecto.
2. Abre [src/app/modules/users/service.py](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/src/app/modules/users/service.py) y busca `existing = await self.users.get_by_email(data.email)`. Fíjate en por qué aparece `if existing is not None:` justo debajo: qué pasaría con `mypy` si intentaras leer `existing.id` sin ese `if`.

---

## Módulo 3: Programación Asíncrona (`async` / `await`)

### Conceptos clave
- `async def` define una **corutina** (una función que puede pausarse mientras espera I/O: red, base de datos, RabbitMQ).
- `await` le dice a Python: *"pausa esta tarea hasta que termine esta espera y atiende otras mientras tanto"*.
- `asyncio.gather(t1, t2, t3)` ejecuta varias esperas en paralelo en lugar de una tras otra.

### Ejemplo ejecutable (medición real de tiempo)
```powershell
@'
import asyncio
import time

async def consultar_servicio(nombre: str) -> str:
    await asyncio.sleep(1.0)  # Simula espera de red/BD de 1 segundo
    return f"{nombre} listo"

async def main() -> None:
    inicio = time.perf_counter()
    # Secuencial: tarda ~2 segundos
    await consultar_servicio("Postgres")
    await consultar_servicio("RabbitMQ")
    print(f"Secuencial: {time.perf_counter() - inicio:.2f}s")

    inicio = time.perf_counter()
    # Concurrente (como en /health/ready o worker.py): tarda ~1 segundo
    resultados = await asyncio.gather(
        consultar_servicio("Postgres"),
        consultar_servicio("RabbitMQ"),
    )
    print(f"Concurrente ({resultados}): {time.perf_counter() - inicio:.2f}s")

asyncio.run(main())
'@ | docker compose exec -T api python -
```

### Ejercicio 3
1. Cambia el `gather` anterior para ejecutar **5** consultas concurrentes de `1.0` segundo cada una y verifica que el tiempo total sigue siendo ~`1.0s` y no `5.0s`.
2. Revisa [src/app/core/health.py](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/src/app/core/health.py) y [src/app/worker.py](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/src/app/worker.py) para ubicar dónde usamos `asyncio.timeout` y `asyncio.gather`.

---

## Módulo 4: Puertos y Adaptadores con `Protocol`

### Conceptos clave
Un `Protocol` define **qué métodos debe tener un objeto**, sin importar qué clase sea. Así tu lógica de negocio depende del contrato (`EmailSender` o `EventPublisher`), no de RabbitMQ ni de AWS.

### Ejemplo ejecutable
```powershell
@'
from typing import Protocol

class Notificador(Protocol):
    def enviar(self, destino: str, mensaje: str) -> None: ...

class NotificadorConsola:
    def enviar(self, destino: str, mensaje: str) -> None:
        print(f"[CONSOLA] Para {destino}: {mensaje}")

class NotificadorMemoria:
    def __init__(self) -> None:
        self.enviados: list[tuple[str, str]] = []

    def enviar(self, destino: str, mensaje: str) -> None:
        self.enviados.append((destino, mensaje))

def procesar_alerta(notificador: Notificador, usuario: str) -> None:
    notificador.enviar(usuario, "Tu leche caduca mañana")

consola = NotificadorConsola()
memoria = NotificadorMemoria()

procesar_alerta(consola, "ana@test.com")
procesar_alerta(memoria, "luis@test.com")
print("Guardados en memoria:", memoria.enviados)
'@ | docker compose exec -T api python -
```

### Ejercicio 4
1. Agrega una tercera clase `NotificadorMayusculas` que cumpla el protocolo `Notificador` e imprima el mensaje en mayúsculas (`.upper()`), y pásala a `procesar_alerta(...)` sin modificar `procesar_alerta`.
2. Compara esto con [src/app/shared/ports.py](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/src/app/shared/ports.py) y [src/app/shared/adapters/smtp_email.py](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/src/app/shared/adapters/smtp_email.py).

---

## Módulo 5: Validación de Contratos con Pydantic v2

### Conceptos clave
- `BaseModel`: valida automáticamente tipos, rangos (`Field(min_length=8)`), correos (`EmailStr`) y rechaza campos no declarados (`extra="forbid"`).
- `@field_validator`: te permite limpiar datos (ej. `.strip().lower()`) o aplicar validaciones personalizadas (ej. `ZoneInfo(value)`).
- Si algo falla, lanza `ValidationError` con detalles exactos de qué campo falló.

### Ejemplo ejecutable (usando el esquema real del proyecto)
```powershell
@'
from pydantic import ValidationError
from app.modules.users.schemas import UserRegisterRequest

valido = UserRegisterRequest(
    email="  Ana@Example.COM ",
    password="PasswordSegura123!",
    full_name="  Ana Lopez  ",
    timezone="America/Mexico_City",
    alert_days_before=3,
)
print("Normalizado:", valido.model_dump(exclude={"password"}))

try:
    UserRegisterRequest(
        email="no-es-correo",
        password="123",
        full_name="A",
        timezone="Planeta/Marte",
        alert_days_before=99,
    )
except ValidationError as exc:
    print(f"Errores detectados ({exc.error_count()}):")
    for err in exc.errors():
        print(f" - campo={err['loc'][0]}: {err['msg']}")
'@ | docker compose exec -T api python -
```

### Ejercicio 5
Prueba pasar un campo extra no permitido (ej. `rol="admin"`) dentro de `UserRegisterRequest.model_validate({...})` y verifica qué error produce gracias a `ConfigDict(extra="forbid")`.

---

## Módulo 6: FastAPI e Inyección de Dependencias (`Depends`)

### Conceptos clave
- Un decorador como `@app.get("/saludo")` registra una URL HTTP.
- `Depends(mi_dependencia)` le pide a FastAPI que ejecute `mi_dependencia()` antes de tu endpoint y te entregue el resultado.
- En pruebas (`pytest`), `app.dependency_overrides[real] = falsa` te permite cambiar una BD o RabbitMQ real por un simulador en 1 línea.

### Ejemplo ejecutable
```powershell
@'
from typing import Annotated
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

def obtener_saludo_base() -> str:
    return "Hola desde producción"

@app.get("/saludo")
def saludar(saludo: Annotated[str, Depends(obtener_saludo_base)]) -> dict[str, str]:
    return {"mensaje": saludo}

with TestClient(app) as client:
    print("Normal:", client.get("/saludo").json())
    app.dependency_overrides[obtener_saludo_base] = lambda: "Hola desde test"
    print("Con override:", client.get("/saludo").json())
'@ | docker compose exec -T api python -
```

### Ejercicio 6
Abre [tests/unit/test_health.py](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/tests/unit/test_health.py) y observa cómo usamos exactamente este mismo patrón `dependency_overrides` para simular que RabbitMQ falló y comprobar que `/health/ready` devuelve `503`.

---

## Módulo 7: SQLAlchemy Async y Transacciones (`commit` vs `rollback`)

### Conceptos clave
- `AsyncSession`: representa una conversación con PostgreSQL.
- `session.add(obj)`: prepara un `INSERT` en memoria.
- `await session.flush()`: envía el `INSERT` a PostgreSQL dentro de la transacción abierta (así obtienes IDs o validas constraints únicos) **sin confirmarlo todavía**.
- `await session.commit()`: guarda todo permanentemente.
- `await session.rollback()`: deshace todo lo hecho desde el último `commit`.

### Ejemplo ejecutable (contra la BD `despensa_test` sin tocar tus datos)
```powershell
@'
import asyncio
from sqlalchemy import select
from app.core.config import get_settings
from app.core.database import create_db_engine, create_session_factory
from app.modules.users.models import User

async def demo() -> None:
    url = get_settings().database_url.replace("/despensa", "/despensa_test")
    engine = create_db_engine(url)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        nuevo = User(
            email="rollback_demo@test.local",
            full_name="Demo Rollback",
            password_hash="hash-demo",
        )
        session.add(nuevo)
        await session.flush()
        print("Dentro de transacción (antes de rollback), ID generado:", nuevo.id)

        await session.rollback()  # Deshacemos todo!

        encontrado = (
            await session.execute(select(User).where(User.email == "rollback_demo@test.local"))
        ).scalar_one_or_none()
        print("Después de rollback en BD:", encontrado)

    await engine.dispose()

asyncio.run(demo())
'@ | docker compose exec -T api python -
```
*(Nota: si aún no habías corrido `pytest` nunca, ejecuta primero `docker compose exec -T api pytest tests/integration -v` para que exista la BD `despensa_test`).*

### Ejercicio 7
1. Ejecuta el ejemplo anterior y confirma que `encontrado` es `None` tras el `rollback()`.
2. Revisa [src/app/modules/users/service.py](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/src/app/modules/users/service.py) y ubica dónde se usa `flush()`, `commit()` y `rollback()` dentro de `register_user`.

---

## Módulo 8: RabbitMQ en 25 Líneas (`aio_pika`)

### Conceptos clave
- **Publisher** envía un `Message` a un **Exchange** con una `routing_key`.
- **Queue** está ligada (*bound*) al Exchange con un patrón (ej. `demo.*`).
- **Consumer** lee de la cola y confirma con `ack()` para borrarlo de la cola, o `nack(requeue=False)` para enviarlo a la Dead Letter Queue (si tiene DLX).

### Ejemplo ejecutable (en tu RabbitMQ real usando una cola temporal)
```powershell
@'
import asyncio
import aio_pika
from app.core.config import get_settings

async def demo_rabbitmq() -> None:
    conn = await aio_pika.connect_robust(get_settings().rabbitmq_url)
    async with conn:
        channel = await conn.channel()
        exchange = await channel.declare_exchange("demo.exchange", aio_pika.ExchangeType.TOPIC)
        queue = await channel.declare_queue(exclusive=True)  # Se borra al cerrar
        await queue.bind(exchange, routing_key="despensa.*")

        await exchange.publish(
            aio_pika.Message(body=b'{"evento": "leche_agregada"}'),
            routing_key="despensa.item_added",
        )
        msg = await queue.get(timeout=5)
        async with msg.process():  # Hace ACK automático al terminar el bloque sin error
            print("Recibido desde RabbitMQ:", msg.body.decode(), "| routing_key:", msg.routing_key)

asyncio.run(demo_rabbitmq())
'@ | docker compose exec -T api python -
```

### Ejercicio 8
Cambia el `routing_key` del `publish` a `"otro.evento"` (que no coincide con `"despensa.*"`), ejecuta de nuevo y observa qué excepción ocurre en `queue.get(timeout=2)` (pista: el mensaje se descarta porque ninguna cola escuchaba ese patrón).

---

## Módulo 9: Testing con `pytest` (Arrange – Act – Assert)

### Conceptos clave
Todo buen test sigue 3 pasos:
1. **Arrange (Preparar):** crea datos de prueba o *mocks*.
2. **Act (Actuar):** llama a la función o endpoint.
3. **Assert (Verificar):** comprueba el resultado esperado.

### Ejemplo de test unitario (puedes leerlo en [tests/unit/test_security.py](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/tests/unit/test_security.py))
- `test_argon2_hash_and_verify` prepara una clave, llama a `hash_password`, y verifica que el hash empiece con `$argon2` y que `verify_password` distinga entre clave correcta e incorrecta.

### Ejercicio 9
1. Corre por separado los tests unitarios vs los de integración para notar la diferencia de velocidad:
   ```powershell
   docker compose exec -T api pytest tests/unit -v
   docker compose exec -T api pytest tests/integration -v
   ```
2. Agrega un test pequeño al final de [tests/unit/test_user_schemas.py](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/tests/unit/test_user_schemas.py) que verifique que `alert_days_before=0` o `alert_days_before=31` falla validación (`ValidationError`), ejecútalo con `pytest` y pasa `ruff check .` para comprobar estilo.
