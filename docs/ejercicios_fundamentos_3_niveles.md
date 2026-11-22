# Banco Completo de Ejercicios: Fundamentos de Programación en 3 Etapas

Este cuaderno reúne **todos los fundamentos esenciales de programación** aplicados al contexto real de tu app **Despensa** y comparados con cómo los usan aplicaciones populares (**Amazon, Spotify, Stripe, Uber, Netflix, Duolingo**).

> **Cómo practicar cada ejercicio en PowerShell:**  
> Puedes ejecutar los ejemplos y tus soluciones directamente dentro de tu contenedor `api`:
> ```powershell
> @'
> # Tu código Python aquí
> print("Listo para practicar")
> '@ | docker compose exec -T api python -
> ```

---

## Etapa 1 (Básica): Lógica, Tipos, Condicionales, Ciclos y Listas

### 1.1 Tipos de Datos, `Decimal` vs `float` y Booleanos *(Como MyFitnessPal / Bancos)*
En apps de nutrición o compras, usar `float` para cantidades exactas puede producir imprecisiones binarias (`0.1 + 0.2 == 0.30000000000000004`). Para cantidades críticas o dinero se usa `Decimal`.

- **Ejercicio B1:** Escribe un script que sume `0.1 + 0.2` con `float` y con `Decimal("0.1") + Decimal("0.2")` e imprima la diferencia.
- **Ejercicio B2:** Dadas las variables `cantidad_actual = 0.25`, `cantidad_minima = 0.5`, `esta_abierto = True` y `dias_restantes = 2`, crea una expresión booleana `necesita_recompra` que sea `True` si queda menos del mínimo **o** si está abierto y vence en `<= 2` días.

### 1.2 Normalización de Strings *(Como el Buscador de Amazon / Gmail)*
Cuando un usuario escribe `"  Leche   DESLACTOSADA  "` desde el móvil, tu backend debe normalizarlo antes de buscar o guardar para evitar duplicados.

- **Ejercicio B3:** Limpia el texto `"   Jitomate   Rojo  Orgánico   "` para convertirlo en `"jitomate rojo orgánico"` (minúsculas y un solo espacio entre palabras — pista: `" ".join(texto.split()).lower()`).
- **Ejercicio B4:** Dada la cadena `"Arroz Blanco|2.5|kg|alacena"`, sepárala con `.split("|")`, convierte el peso a `float` y muestra un `f-string`: `"Producto: Arroz Blanco (2.5 kg) en alacena"`.

### 1.3 Condicionales y *Guard Clauses* (*Early Return*) *(Como Uber / Rappi)*
En lugar de anidar `if` dentro de `if` (difícil de leer), las apps profesionales validan primero los casos de error y salen rápido (*early return*).

- **Ejercicio B5:** Escribe una función `clasificar_caducidad(dias_restantes: int) -> str` usando *guard clauses* (sin `else` anidados):
  - `< 0` → `"VENCIDO"`
  - `== 0` → `"VENCE_HOY"`
  - `<= 3` → `"URGENTE"`
  - `<= 7` → `"PROXIMO"`
  - mayor a 7 → `"FRESCO"`
- **Ejercicio B6:** Pruébala con la lista `[-2, 0, 1, 5, 20]` usando un `for`.

### 1.4 Ciclos `for`, `while`, `enumerate` y `zip` *(Como Tickets de Supermercado)*
- **Ejercicio B7:** Tienes dos listas paralelas: `productos = ["Leche", "Huevo", "Pan"]` y `cantidades = [2, 12, 1]`. Usa `zip()` y `enumerate(start=1)` para imprimir:
  `1. Leche -> 2`, `2. Huevo -> 12`, `3. Pan -> 1`.
- **Ejercicio B8 (Simular reintentos con `while`):** Simula un servicio inestable que falla los primeros 2 intentos y responde `"OK"` en el 3ro. Usa un ciclo `while` con `max_intentos = 5` para reintentar hasta lograr `"OK"` o agotar intentos.

### 1.5 Listas, Slicing, `any()` y `all()` *(Como Spotify Playlists)*
- **Ejercicio B9:** Dada `dias = [10, 2, 0, -1, 5, 3]`:
  - Verifica con `any(...)` si existe **al menos un** producto vencido (`< 0`).
  - Verifica con `all(...)` si **todos** vencen en menos de 30 días.
  - Usa una *list comprehension* para obtener solo los que vencen entre `0` y `3` días inclusive.

---

## Etapa 2 (Intermedia): Estructuras, Funciones, POO y Manejo de Errores

### 2.1 Diccionarios, `defaultdict` y `Counter` *(Como Carrito de Amazon / Inventario)*
- **Ejercicio I1 (Agrupación):** Dada la lista de tuplas:
  `compras = [("refrigerador", "Leche"), ("alacena", "Arroz"), ("refrigerador", "Yogurt"), ("congelador", "Pollo"), ("alacena", "Pasta")]`
  Agrúpalas en un diccionario por ubicación usando `collections.defaultdict(list)` para obtener `{"refrigerador": ["Leche", "Yogurt"], ...}`.
- **Ejercicio I2 (Suma de stock por producto):** Tienes múltiples lotes:
  `lotes = [("Leche", 1.0), ("Huevo", 6.0), ("Leche", 0.5), ("Huevo", 12.0)]`
  Calcula el total disponible por cada producto en un diccionario (`{"Leche": 1.5, "Huevo": 18.0}`).

### 2.2 Conjuntos (`set`) para Comparar Despensa vs Recetas *(Como Apps de Cocina)*
- **Ejercicio I3:**
  - `mi_despensa = {"huevo", "leche", "harina", "sal", "tomate"}`
  - `recetas = {"Hotcakes": {"huevo", "leche", "harina", "mantequilla"}, "Omelette": {"huevo", "queso", "sal"}}`
  - Recorre `recetas` e imprime para cada una: ingredientes que ya tienes (`&`), ingredientes que te faltan (`-`) y porcentaje de coincidencia.

### 2.3 Funciones, Trampa del Argumento Mutable, Lambdas y Recursividad
- **Ejercicio I4 (Bug clásico de Python):** Ejecuta y entiende por qué esto es un bug famoso:
  ```python
  def agregar_mal(item: str, lista: list[str] = []) -> list[str]:
      lista.append(item)
      return lista
  ```
  Corrígelo usando `lista: list[str] | None = None` (crear `[]` dentro si es `None`).
- **Ejercicio I5 (Ordenamiento multi-criterio):** Ordena una lista de diccionarios `[{"nombre": "Queso", "dias": 3, "cantidad": 2}, {"nombre": "Leche", "dias": 3, "cantidad": 1}, {"nombre": "Yogurt", "dias": 1, "cantidad": 4}]` primero por `dias` ascendente y, en empate, por `cantidad` ascendente usando `sorted(..., key=lambda x: (x["dias"], x["cantidad"]))`.
- **Ejercicio I6 (Recursividad — como carpetas de Google Drive):** Dado un árbol de categorías de alimentos:
  ```python
  categorias = {
      "Alimentos": {
          "Lácteos": {"Leche": {}, "Quesos": {"Oaxaca": {}, "Panela": {}}},
          "Granos": {"Arroz": {}, "Frijol": {}},
      }
  }
  ```
  Escribe una función recursiva `listar_hojas(nodo)` que devuelva todas las categorías finales (las que tienen `{}` vacío): `["Leche", "Oaxaca", "Panela", "Arroz", "Frijol"]`.

### 2.4 Excepciones Personalizadas y Context Managers *(Como Stripe / Transacciones)*
- **Ejercicio I7:** Crea dos excepciones `DespensaError(Exception)` y `StockInsuficienteError(DespensaError)`. Escribe una función que las lance y un bloque `try / except StockInsuficienteError / except DespensaError / finally` que imprima siempre `"Cerrando operación"`.

### 2.5 POO: Encapsulación, Dunder Methods y Polimorfismo *(Como Rappi / DoorDash)*
- **Ejercicio I8:** Crea una clase `ProductoDespensa` con:
  - `__init__(self, nombre: str, cantidad: float)`
  - `@property` `cantidad` (solo lectura externa; modificable solo mediante `agregar()` y `consumir()`)
  - `__repr__` legible (`ProductoDespensa(nombre='Leche', cantidad=1.5)`)
  - `__eq__` para comparar si dos instancias representan el mismo producto por `nombre.lower()`.
- **Ejercicio I9 (Polimorfismo sin herencia rígida):** Crea 2 clases distintas `CanalEmail` y `CanalPush` que implementen `enviar(self, usuario: str, mensaje: str) -> str`. Crea una lista `[CanalEmail(), CanalPush()]` y recórrela enviando la misma alerta de caducidad por ambos canales.

---

## Etapa 3 (Avanzada): Algoritmos Reales y Patrones de Producción

### 3.1 Algoritmo de Recomendación Ponderada (*Scoring*) *(Como Netflix / Spotify)*
En nuestra **Etapa 4**, no basta con contar ingredientes: queremos **salvar comida antes de que caduque**.

- **Ejercicio A1:** Implementa `ranquear_recetas(despensa, recetas)`:
  - `despensa`: `{"huevo": 2, "leche": 1, "tomate": 3, "pollo": 5}` *(el número son días para caducar)*.
  - `recetas`: diccionario de recetas con sus ingredientes requeridos.
  - **Fórmula de puntaje:**
    - `+10` puntos por cada ingrediente que sí tienes.
    - `+25` puntos **extra** si ese ingrediente caduca en `<= 3` días.
    - `-15` puntos por cada ingrediente que te falta.
  - Devuelve las recetas ordenadas de mayor a menor puntaje.

### 3.2 Algoritmo FEFO Atómico (*All-or-Nothing*) *(Como Amazon FBA / Farmacias)*
- **Ejercicio A2:** Tienes una lista de lotes ordenados por fecha:
  `lotes = [{"id": "A", "qty": 2, "dias": 1}, {"id": "B", "qty": 5, "dias": 4}, {"id": "C", "qty": 3, "dias": 10}]`
  Escribe `consumir_atomico(lotes, cantidad)`:
  1. Primero verifica si el stock total alcanza; si no alcanza, lanza `ValueError` **sin modificar ningún lote** (atomicidad).
  2. Si alcanza, descuenta en orden FEFO (`A` primero, luego `B`, etc.) y devuelve el detalle de cuánto se tomó de cada lote (ej. si pides `4`, toma `2` de `A` y `2` de `B`).

### 3.3 Rate Limiter (Ventana Deslizante) + Backoff Exponencial *(Como Cloudflare / AWS SDK)*
- **Ejercicio A3:**
  1. Implementa una clase `RateLimiter(max_peticiones=3, ventana_seg=5)` usando `collections.deque` y `time.monotonic()` que permita 3 llamadas rápidas y devuelva `False` en la 4ta dentro de los 5 segundos.
  2. Escribe una función `calcular_espera_backoff(intento: int, base: float = 0.5) -> float` que retorne `base * (2 ** intento) + jitter_aleatorio` (usando `random.uniform(0, 0.2)`), explicando por qué el *jitter* evita que miles de apps móviles reintenten al mismo milisegundo (*Thundering Herd*).

### 3.4 Caché en Memoria con TTL e Invalidación *(Como Redis)*
- **Ejercicio A4:** Crea una clase `SimpleTTLCache` con:
  - `set(key, value, ttl_seconds)` (guarda `(value, time.monotonic() + ttl_seconds)`)
  - `get(key)` (si expiró, la borra y retorna `None`)
  - `invalidate(key)` (para simular cuando llega un evento `pantry.item_added` y borra el caché del usuario).

### 3.5 Mini-Broker de Eventos con Idempotencia y DLQ *(Como RabbitMQ / SQS)*
- **Ejercicio A5:** Simula en Python puro (sin Docker extra) la arquitectura completa de eventos usando `deque`:
  - `cola_principal = deque()`
  - `dlq = deque()`
  - `eventos_procesados = set()`
  1. Encola 3 eventos: uno válido, uno **duplicado** (mismo `event_id`) y uno corrupto (`{"malformed": True}`).
  2. Procesa la cola: si `event_id` ya está en `eventos_procesados`, ignóralo (idempotencia); si falla 3 veces al procesarse, muévelo a `dlq`. Al final imprime `eventos_procesados` y `dlq`.

### 3.6 Concurrencia Limitada con `asyncio.Semaphore` y `asyncio.Lock` *(Como Notificadores Masivos)*
- **Ejercicio A6:** Imagina que a las 8:00 AM debes enviar **10** correos/push de caducidad, pero el proveedor externo solo permite **3 conexiones simultáneas**.
  - Crea una corutina `enviar_alerta(usuario_id, sem, contador_lock)` que adquiera `async with sem:` (`asyncio.Semaphore(3)`), espere `0.5s`, incremente un contador compartido protegido por `async with lock:`, y ejecuta las 10 tareas con `asyncio.gather`. Comprueba que tarda ~`2.0s` (4 tandas de máximo 3) en lugar de `5.0s` secuenciales o `0.5s` sin límite.

---

## Solución de Referencia (Ejemplo Completo del Ejercicio A1 + A2)

Cuando intentes resolver los ejercicios por tu cuenta, puedes comparar tu enfoque con este ejemplo ejecutable de la Etapa 3:

```powershell
@'
def ranquear_recetas(
    despensa: dict[str, int],
    recetas: dict[str, set[str]],
) -> list[tuple[str, int]]:
    ranking: list[tuple[str, int]] = []
    for nombre, ingredientes in recetas.items():
        puntaje = 0
        for ing in ingredientes:
            if ing in despensa:
                puntaje += 10
                if despensa[ing] <= 3:
                    puntaje += 25  # Prioridad por caducidad próxima
            else:
                puntaje -= 15
        ranking.append((nombre, puntaje))
    return sorted(ranking, key=lambda item: item[1], reverse=True)

mi_despensa = {"huevo": 2, "leche": 6, "tomate": 1, "sal": 30}
mis_recetas = {
    "Huevos con tomate": {"huevo", "tomate", "sal"},
    "Licuado": {"leche", "platano", "avena"},
    "Omelette": {"huevo", "queso", "sal"},
}
print("Ranking de recetas:", ranquear_recetas(mi_despensa, mis_recetas))
'@ | docker compose exec -T api python -
```
