# Python desde Cero: Bases Completas para Resolver Todos los Ejercicios

No necesitas saber nada de Python para empezar aquí. Esta guía te da **todas las piezas básicas del lenguaje** con ejemplos cortos para que luego puedas resolver sin trabas los ejercicios de [ejercicios_fundamentos_3_niveles.md](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docs/ejercicios_fundamentos_3_niveles.md).

> **Cómo probar cualquier ejemplo en tu terminal PowerShell:**
> ```powershell
> @'
> print("Hola Python desde Docker")
> '@ | docker compose exec -T api python -
> ```

---

## 1. Reglas Básicas de Sintaxis

1. **Sin punto y coma (`;`) ni llaves (`{}`):** Python usa **4 espacios de indentación** para definir qué código está dentro de un `if`, `for`, `def` o `class`.
2. **Comentarios:** todo lo que empieza con `#` es ignorado por Python (sirve para notas).
3. **Imprimir en pantalla:** `print("texto")` o con **`f-strings`** para mezclar texto y variables:
   ```python
   producto = "Leche"
   dias = 3
   print(f"Tu {producto} vence en {dias} días")
   ```

---

## 2. Variables, Tipos Primitivos y Operadores

En Python no declaras `int x = 5`; simplemente asignas el valor:

```python
cantidad = 2            # int (entero)
litros = 1.5            # float (decimal aproximado)
nombre = "Arroz"        # str (texto, comillas simples o dobles)
abierto = True          # bool (True o False, siempre con mayúscula inicial)
fecha_baja = None       # None (ausencia de valor, equivalente a null)
```

### Operadores clave
- **Matemáticos:** `+`, `-`, `*`, `/` (división decimal), `//` (división entera), `%` (residuo/módulo), `**` (potencia: `2 ** 3 == 8`).
- **Comparación:** `==`, `!=`, `<`, `<=`, `>`, `>=`.
- **Para `None` siempre usa `is`:** `if fecha_baja is None:` o `if fecha_baja is not None:`.
- **Lógicos:** `and`, `or`, `not` (en Python se escriben con palabras, no `&&` ni `||` ni `!`).
- **Exactitud decimal (`Decimal`):** cuando necesitas precisión exacta (dinero o gramos sin errores de redondeo binario como `0.1 + 0.2 = 0.30000000000000004`), importa `from decimal import Decimal` y usa `Decimal("0.1") + Decimal("0.2")`.

---

## 3. Strings (Texto) y Métodos Más Usados

```python
texto = "  Leche   Entera  "
texto.strip()           # Quita espacios al inicio y final -> "Leche   Entera"
texto.lower()           # Minúsculas -> "  leche   entera  "
texto.split()           # Separa por espacios en una lista -> ["Leche", "Entera"]
" ".join(["a", "b"])    # Une una lista con espacios -> "a b"
"Arroz|2|kg".split("|") # Separa por un carácter -> ["Arroz", "2", "kg"]
"leche" in "leche entera"  # True (verifica si contiene una subcadena)
```

---

## 4. Condicionales (`if` / `elif` / `else`)

```python
dias = 2
if dias < 0:
    estado = "VENCIDO"
elif dias <= 3:
    estado = "URGENTE"
else:
    estado = "FRESCO"
```
**Buena práctica (*Guard Clause*):** dentro de una función, si detectas un caso especial, haz `return` de inmediato en lugar de anidar `else`.

---

## 5. Estructuras de Datos (Las 4 Colecciones Esenciales)

| Estructura | Sintaxis | Ordenada | Mutable | Duplicados | Uso típico en Despensa |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`list`** | `["a", "b"]` | Sí | Sí | Sí | Lotes ordenados por fecha |
| **`tuple`** | `("a", 1)` | Sí | No | Sí | Pares fijos (nombre, puntaje) |
| **`dict`** | `{"leche": 2}` | Sí | Sí | Claves no | Inventario `{ingrediente: dias}` |
| **`set`** | `{"sal", "pan"}` | No | Sí | No | Comparar ingredientes (`&`, `-`) |

### Operaciones básicas en cada una
```python
# LISTAS
items = ["leche", "pan"]
items.append("huevo")    # Agrega al final
primero = items[0]       # Índice 0 ("leche")
ultimo = items[-1]       # Último elemento ("huevo")
sublista = items[0:2]    # Slicing: elementos 0 y 1
total = len(items)       # Largo: 3

# DICCIONARIOS
stock = {"leche": 2, "pan": 1}
stock["huevo"] = 12              # Agregar o actualizar clave
valor = stock.get("queso", 0)    # Lee seguro: si no existe devuelve 0 (sin error)
if "leche" in stock:             # Verifica si existe la clave
    print(stock["leche"])

# CONJUNTOS (SET)
tengo = {"huevo", "sal", "leche"}
receta = {"huevo", "sal", "queso"}
en_comun = tengo & receta        # {"huevo", "sal"}
me_falta = receta - tengo        # {"queso"}
```

**Herramientas extra de `collections`:**
- `from collections import defaultdict`: crea un valor por defecto automáticamente si una clave no existe (ej. `grupos = defaultdict(list)` y luego `grupos["refrigerador"].append("Leche")`).
- `from collections import deque`: cola rápida para agregar/sacar por ambos extremos (`append`, `popleft`).

---

## 6. Ciclos (`for`, `while`) y Comprensiones

```python
# Recorrer una lista
for item in ["leche", "pan"]:
    print(item)

# Con índice (enumerate) y dos listas a la vez (zip)
for idx, (prod, qty) in enumerate(zip(["Leche", "Pan"], [2, 1]), start=1):
    print(f"{idx}. {prod}: {qty}")

# Recorrer un diccionario
for nombre, dias in {"leche": 2, "arroz": 30}.items():
    print(nombre, dias)

# Ciclo while (mientras se cumpla condición)
intento = 0
while intento < 3:
    intento += 1
    if intento == 2:
        break  # Sale del ciclo inmediatamente

# List comprehension (crear lista filtrada/transformada en 1 línea)
urgentes = [d for d in [10, 2, 0, 5] if d <= 3]  # [2, 0]

# Funciones útiles: any() y all()
hay_urgentes = any(d <= 3 for d in [10, 2, 5])   # True
todos_frescos = all(d > 7 for d in [10, 2, 5])   # False
```

---

## 7. Funciones (`def`), `lambda` y Ordenamiento

```python
def sumar(a: int, b: int = 0) -> int:
    """Suma dos enteros; b vale 0 si no se pasa."""
    return a + b

# Función anónima corta (lambda) usada para ordenar por un campo
lotes = [{"nombre": "B", "dias": 5}, {"nombre": "A", "dias": 1}]
ordenados = sorted(lotes, key=lambda x: x["dias"])  # Primero "A" (1), luego "B" (5)
```
- **Regla de oro:** nunca uses una lista o diccionario vacío como valor por defecto (`def f(x=[])` es un bug porque se comparte entre llamadas). Usa `x: list[str] | None = None` y crea `if x is None: x = []` adentro.

---

## 8. Excepciones (`try / except`) y `raise`

```python
class StockInsuficienteError(Exception):
    pass

def retirar(disponible: int, pedir: int) -> int:
    if pedir > disponible:
        raise StockInsuficienteError("No alcanza el inventario")
    return disponible - pedir

try:
    restante = retirar(2, 5)
except StockInsuficienteError as err:
    print("Error controlado:", err)
finally:
    print("Esto siempre se ejecuta al final")
```

---

## 9. Clases y Programación Orientada a Objetos (POO)

```python
class Lote:
    def __init__(self, nombre: str, cantidad: float) -> None:
        self.nombre = nombre          # Atributo público
        self._cantidad = cantidad     # Convención "_" = interno/privado

    @property
    def cantidad(self) -> float:      # Lectura controlada sin poder asignar directo
        return self._cantidad

    def __repr__(self) -> str:        # Cómo se ve al hacer print(lote)
        return f"Lote(nombre={self.nombre!r}, cantidad={self._cantidad})"

    def __eq__(self, other: object) -> bool:  # Define qué significa lote1 == lote2
        if not isinstance(other, Lote):
            return False
        return self.nombre.lower() == other.nombre.lower()
```

---

## 10. Módulos Estándar Indispensables para los Ejercicios

- **`datetime` y `zoneinfo`:** `datetime.now(UTC)`, `date.today()`, `timedelta(days=3)`, `ZoneInfo("America/Mexico_City")`.
- **`time` y `random`:** `time.monotonic()` (medir intervalos sin saltos de reloj), `random.uniform(0, 0.2)` (para *jitter*).
- **`asyncio`:** `async def`, `await asyncio.sleep(0.5)`, `asyncio.gather(...)`, `asyncio.Semaphore(3)`, `asyncio.Lock()`.

---

## 11. `import`, Paquetes (`__init__.py`) y `PYTHONPATH`

En Python, reutilizas código de otros archivos o librerías con `import`:

```python
import math                          # Importa todo el módulo: usas math.ceil(1.2)
from datetime import date, timedelta # Importa solo dos clases: usas date.today()
from app.core.config import Settings # Importa desde nuestro paquete src/app/
```

### Reglas clave para que tus `import` nunca fallen
1. **Carpetas = Paquetes:** toda carpeta dentro de `src/app/` tiene un archivo `__init__.py` (aunque esté vacío) para que Python la reconozca como paquete importable.
2. **Por qué funciona `from app.core...`:** en [docker-compose.yml](file:///c:/Users/buda_/Documents/AI_projects/Despnsa%20project/docker-compose.yml), definimos `PYTHONPATH: /app/src`, que le dice a Python *"busca paquetes empezando dentro de `/app/src`"*.
3. **Usa siempre imports absolutos (`from app.modules...`):** en lugar de relativos (`from ..core...`), porque son más claros y evitan confusiones al mover archivos.
4. **Evita *Circular Imports*:** si `A.py` importa a `B.py` y `B.py` importa a `A.py`, Python falla al arrancar. Por eso nuestras capas van en una sola dirección: `router -> service -> repository -> models`.

---

## 12. Cómo Correr tus Ejercicios (3 Formas Prácticas)

Todas corren **dentro del contenedor `api`** (no necesitas instalar Python en Windows):

### Forma 1: Bloques rápidos desde PowerShell *(Recomendada para `B1`–`A6`)*
Pegas el código entre `@'` y `'@` y se ejecuta al instante:
```powershell
@'
nombre = "Despensa"
print(f"Probando en {nombre}")
'@ | docker compose exec -T api python -
```

### Forma 2: Consola interactiva de Python (*REPL*)
Ideal para probar una línea a la vez (`exit()` para salir):
```powershell
docker compose exec api python
```

### Forma 3: Archivo temporal de práctica (si quieres escribir en VS Code)
Si prefieres editar un archivo largo en tu editor:
1. Crea un archivo temporal dentro de `tests/scratch_practica.py` *(como `tests/` está montado en Docker, el contenedor lo ve al instante)*.
2. Ejecútalo con:
   ```powershell
   docker compose exec -T api python tests/scratch_practica.py
   ```
3. **Importante:** bórralo antes de hacer `git add` / `commit` para mantener limpio el repositorio.

---

## 13. Convenciones de Estilo en Python (PEP 8 + `ruff`)

En Python el estilo es parte del estándar profesional (y `ruff` lo valida automáticamente en cada PR):

| Elemento | Convención | Ejemplo real en este proyecto |
| :--- | :--- | :--- |
| **Variables y funciones** | `snake_case` (minúsculas con guión bajo) | `register_user`, `alert_days_before` |
| **Clases y Excepciones** | `PascalCase` | `UserService`, `DomainError` |
| **Constantes globales** | `UPPER_SNAKE_CASE` | `EVENTS_EXCHANGE`, `WELCOME_EMAIL_QUEUE` |
| **Atributos/métodos internos** | Prefijo `_` | `self._exchange`, `_issue_tokens` |
| **Largo máximo de línea** | 100 caracteres (en `pyproject.toml`) | Evita líneas gigantes difíciles de leer |
| **Orden de `import`** | 1) Librería estándar, 2) Terceros, 3) `app.*` | `ruff check --fix` los ordena solo |

---

## 14. Problemas Comunes de Principiantes (y Cómo Resolverlos)

1. **`IndentationError: unexpected indent` / `expected an indented block`:**
   - **Causa:** mezclaste espacios y *tabs*, o dejaste un `if`/`def` sin bloque indentado debajo.
   - **Solución:** usa siempre **4 espacios** por nivel (en VS Code aparece abajo a la derecha `Spaces: 4`).
2. **`SyntaxError: expected ':'`:**
   - **Causa:** olvidaste los dos puntos `:` al final de `if`, `elif`, `else`, `for`, `while`, `def` o `class`.
3. **`ModuleNotFoundError: No module named 'app'`:**
   - **Causa:** corriste Python fuera de Docker o sin `PYTHONPATH=/app/src`.
   - **Solución:** ejecuta siempre con `docker compose exec -T api python ...`.
4. **`AttributeError: 'NoneType' object has no attribute '...'`:**
   - **Causa:** una búsqueda (ej. `get_by_email`) devolvió `None` e intentaste leer `.email` o `.id` sin validar antes.
   - **Solución:** verifica `if user is None:` antes de usar sus atributos (`mypy` te avisa de esto antes de correr el programa).
5. **`KeyError: 'queso'`:**
   - **Causa:** buscaste `diccionario["queso"]` y esa clave no existe.
   - **Solución:** usa `diccionario.get("queso", 0)` o verifica `if "queso" in diccionario:`.
6. **`RuntimeWarning: coroutine '...' was never awaited`:**
   - **Causa (muy común en FastAPI/SQLAlchemy):** llamaste a una función `async def` olvidando poner `await` delante.
   - **Solución:** agrega `await` (`user = await self.users.get_by_email(...)`).
7. **Modificar una lista mientras la recorres (`for x in lista: lista.remove(x)`):**
   - **Causa:** al borrar elementos, los índices se recorren y Python se salta elementos.
   - **Solución:** crea una lista nueva filtrada: `activos = [x for x in lista if x.cantidad > 0]`.

---

## Mapa Rápido: Qué Sección Repasar Antes de Cada Ejercicio

| Bloque de Ejercicios | Secciones de esta guía que necesitas |
| :--- | :--- |
| **B1 – B2** (`Decimal`, booleanos) | Secciones **1 y 2** |
| **B3 – B4** (strings, split, f-strings) | Sección **3** |
| **B5 – B6** (condicionales y guard clauses) | Sección **4** |
| **B7 – B9** (`for`, `while`, `zip`, `any/all`) | Secciones **5 y 6** |
| **I1 – I3** (`dict`, `defaultdict`, `set`) | Sección **5** |
| **I4 – I6** (funciones, `lambda`, recursividad) | Sección **7** |
| **I7 – I9** (excepciones y POO) | Secciones **8 y 9** |
| **A1 – A6** (algoritmos, `deque`, `asyncio`) | Secciones **5, 6, 7, 9 y 10** |
