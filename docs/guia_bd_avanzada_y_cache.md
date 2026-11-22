# Guía de Base de Datos Avanzada (PostgreSQL) y Caché

Aunque ya tienes bases de SQL, en un backend profesional orientado a eventos la base de datos no solo guarda filas: protege la integridad de los datos, resuelve concurrencia y debe escalar sin volverse un cuello de botella. Aquí veremos los temas clave que aplicaremos en las **Etapas 2, 3 y 4**, con **ejercicios ejecutables en tu PostgreSQL local**.

> **Seguridad al practicar:** todos los ejercicios SQL de esta guía apuntan a la base de datos de pruebas **`despensa_test`** (nunca a `despensa`), así no afectas tus datos de desarrollo.  
> *(Si aún no existe `despensa_test`, corre una vez `docker compose exec -T api pytest tests/integration -v`).*

---

## 1. Integridad y Constraints (Reglas en la BD)

No confíes solo en que Python valide los datos; la base de datos es la **última línea de defensa**:
- **`PRIMARY KEY` con `UUID` vs `SERIAL`:** usamos `UUID` porque evita que un atacante adivine IDs (`/pantry/items/1`, `/2`, `/3`) y permite generar IDs en el cliente móvil o en Python antes del `INSERT`.
- **`CHECK` Constraints:** en la Etapa 2, un lote de comida nunca puede tener cantidad negativa (`CHECK (quantity >= 0)`). Si hay un bug en código, PostgreSQL frena el dato corrupto.
- **`FOREIGN KEY` (`ON DELETE CASCADE` vs `RESTRICT`):**
  - `refresh_tokens.user_id` usa `ON DELETE CASCADE` (si se borra el usuario, se borran sus tokens).
  - Un catálogo de productos usado por lotes históricos debería usar `RESTRICT` (para no borrar por error un producto que tiene inventario).
- **`UNIQUE` parciales:** por ejemplo, permitir solo un usuario activo con el mismo email (`CREATE UNIQUE INDEX ... WHERE deleted_at IS NULL`) cuando usamos *soft delete*.

---

## 2. Índices y `EXPLAIN ANALYZE`

Sin índices, PostgreSQL hace **Sequential Scan** (lee toda la tabla fila por fila). Con índices, hace **Index Scan** en milisegundos.

### Tipos de índices que usaremos en Despensa
1. **Índice Compuesto `(user_id, expires_at)`:**
   - En la Etapa 3 preguntaremos cada día: *"¿Qué productos del usuario X vencen en los próximos 3 días?"*.
   - **Orden de columnas importa:** primero `user_id` (filtra a un usuario) y luego `expires_at` (filtra por rango de fechas).
2. **Índice Parcial (`WHERE status = 'pending'`):**
   - Nuestra tabla `outbox_events` puede crecer a millones de filas `published`, pero el Worker solo busca las `pending`. Un índice parcial solo indexa las pendientes, ocupando muy poca RAM.
3. **Índice `GIN` para `JSONB`:**
   - Como `outbox_events.payload` es `JSONB`, si alguna vez necesitas buscar dentro del JSON (`WHERE payload @> '{"timezone": "UTC"}'`), un índice `GIN` lo vuelve instantáneo.

---

## 3. Views vs Materialized Views

### 3.1 `VIEW` (Vista Normal)
Es una **consulta SQL guardada con nombre**. No almacena datos físicos; cada vez que haces `SELECT * FROM mi_vista`, PostgreSQL ejecuta la consulta subyacente.
- **Cuándo usarla:** para simplificar reportes o joins repetitivos (ej. unir `pantry_items` + `products` + días restantes para caducar) manteniendo los datos 100% en tiempo real.

### 3.2 `MATERIALIZED VIEW` (Vista Materializada)
**Sí guarda el resultado en disco** como si fuera una tabla snapshot. Es rapidísima para leer analítica pesada (ej. *"ranking mensual de desperdicio por categoría"*), pero los datos quedan congelados hasta que ejecutas `REFRESH MATERIALIZED VIEW CONCURRENTLY mi_vista`.
- **Cuándo usarla:** dashboards pesados donde no importa un retraso de minutos/horas.

---

## 4. Stored Procedures, Functions y Triggers (¿Cuándo SÍ y cuándo NO?)

En arquitectura moderna existe una regla clara para no terminar con lógica de negocio escondida en dos lugares:

| Característica | **Cuándo SÍ usar en PostgreSQL** | **Cuándo NO (dejarlo en Python)** |
| :--- | :--- | :--- |
| **Triggers** | Tareas técnicas automáticas de fila: actualizar `updated_at`, auditoría de cambios. | Reglas de negocio complejas o llamadas externas (enviar emails, publicar a RabbitMQ). |
| **Functions / Procedures** | Mantenimiento masivo dentro de BD (ej. purgar `outbox_events` publicados hace >30 días sin traer 1M de filas a Python). | Validaciones de negocio, flujo de aplicación, manejo de HTTP/eventos (dificultan testing con `pytest` y versionado). |

---

## 5. Concurrencia y Bloqueos (`FOR UPDATE` y `SKIP LOCKED`)

Imagina que tienes **1 litro de leche** y dos peticiones simultáneas intentan consumir 1 litro al mismo tiempo:
1. Sin bloqueo, ambas leen `quantity = 1`, ambas restan `1` y ambas devuelven éxito (¡terminas con `-1` o doble consumo!).
2. **Solución con bloqueo pesimista:**
   ```sql
   SELECT id, quantity FROM pantry_items WHERE id = ... FOR UPDATE;
   ```
   PostgreSQL bloquea esa fila hasta el `COMMIT`: la segunda petición espera unos milisegundos, lee `quantity = 0` y falla limpiamente.
3. **`FOR UPDATE SKIP LOCKED` (el que ya usamos en `OutboxRepository`):**
   Si tienes 2 Workers buscando tareas pendientes en `outbox_events`, el Worker 2 **no espera** sino que **salta** las filas bloqueadas por el Worker 1 y toma las siguientes.

---

## 6. Estrategia de Caché (Redis + Invalidación por Eventos)

En la **Etapa 4**, calcular recetas recomendadas ordenando ingredientes y fechas de caducidad puede ser costoso si el usuario abre la app 20 veces seguidas sin haber cambiado su despensa.

### Patrón *Cache-Aside* (Lectura Perezosa)
1. La API consulta primero en **Redis** (`GET recipes:recommended:{user_id}`).
2. **Cache Hit:** si existe, responde en ~1–2 ms sin tocar PostgreSQL.
3. **Cache Miss:** si no existe, consulta PostgreSQL, calcula las recetas, guarda el resultado en Redis con un **TTL** (ej. `EX 900` = 15 minutos) y responde.

### Invalidación Reactiva Orientada a Eventos
El gran problema del caché es mostrar datos viejos (*stale data*). Como nuestra arquitectura es orientada a eventos:
- Cuando el usuario agrega o consume un alimento, `pantry` emite `pantry.item_added` o `pantry.item_consumed`.
- El Worker de recetas escucha ese evento y ejecuta `DEL recipes:recommended:{user_id}` en Redis. Así el caché siempre se refresca al instante cuando cambia la despensa.

---

## 7. Ejercicios Prácticos en PostgreSQL (`despensa_test`)

Ejecuta estos ejercicios en PowerShell contra `despensa-postgres` usando `psql`:

### Ejercicio BD1: Inspeccionar tablas, índices y planes con `EXPLAIN ANALYZE`
```powershell
docker compose exec postgres psql -U despensa -d despensa_test -c "\d outbox_events"
docker compose exec postgres psql -U despensa -d despensa_test -c "EXPLAIN ANALYZE SELECT id, event_type FROM outbox_events WHERE status = 'pending';"
```
- **Qué debes observar:** busca si dice `Seq Scan` o `Index Scan` (en tablas casi vacías Postgres a veces prefiere `Seq Scan` por ser más rápido en memoria).

### Ejercicio BD2: Crear un Índice Parcial y un Índice `GIN` sobre `JSONB`
```powershell
docker compose exec postgres psql -U despensa -d despensa_test -c "CREATE INDEX IF NOT EXISTS ix_outbox_pending_created ON outbox_events (created_at) WHERE status = 'pending';"
docker compose exec postgres psql -U despensa -d despensa_test -c "CREATE INDEX IF NOT EXISTS ix_outbox_payload_gin ON outbox_events USING GIN (payload);"
docker compose exec postgres psql -U despensa -d despensa_test -c "\di outbox_events*"
```
- **Pregunta:** ¿Por qué `ix_outbox_pending_created` ocupa muchísimo menos espacio que un índice normal sobre toda la tabla?

### Ejercicio BD3: Crear una `VIEW` práctica sobre `outbox_events`
```powershell
docker compose exec postgres psql -U despensa -d despensa_test -c "CREATE OR REPLACE VIEW v_outbox_resumen AS SELECT event_type, status, COUNT(*) AS total FROM outbox_events GROUP BY event_type, status;"
docker compose exec postgres psql -U despensa -d despensa_test -c "SELECT * FROM v_outbox_resumen;"
```

### Ejercicio BD4: Crear una Function + Trigger de `updated_at` automático
Prueba cómo PostgreSQL puede mantener automáticamente `updated_at` cada vez que alguien hace `UPDATE` sobre `users`:
```powershell
docker compose exec postgres psql -U despensa -d despensa_test -c "
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS \$\$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
\$\$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
"
```
- **Reto:** inserta un usuario de prueba en `despensa_test` (o usa uno existente), hazle un `UPDATE full_name = 'Nuevo Nombre'`, y comprueba que `updated_at` cambió solo sin incluirlo en el `UPDATE`.

### Ejercicio BD5: Crear un Stored Procedure (`PROCEDURE`) de mantenimiento
Un procedimiento típico de limpieza de Outbox antiguo (solo borra eventos ya publicados hace más de 30 días):
```powershell
docker compose exec postgres psql -U despensa -d despensa_test -c "
CREATE OR REPLACE PROCEDURE sp_purge_old_outbox(p_days INTEGER)
LANGUAGE plpgsql AS \$\$
BEGIN
    DELETE FROM outbox_events
    WHERE status = 'published'
      AND published_at < NOW() - make_interval(days => p_days);
END;
\$\$;
CALL sp_purge_old_outbox(30);
"
```

### Ejercicio BD6: Simular `FOR UPDATE SKIP LOCKED`
En una sesión de `psql`, abre una transacción y bloquea una fila sin hacer `COMMIT` todavía; luego entiende qué vería un segundo worker si ejecuta `SELECT ... FOR UPDATE SKIP LOCKED`:
```powershell
docker compose exec postgres psql -U despensa -d despensa_test -c "BEGIN; SELECT id, status FROM outbox_events WHERE status = 'pending' LIMIT 1 FOR UPDATE SKIP LOCKED; ROLLBACK;"
```
