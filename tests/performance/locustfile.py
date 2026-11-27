"""Script de pruebas de carga con Locust para validar SLOs de latencia y saturación."""

from uuid import uuid4

from locust import HttpUser, between, task


class DespensaUser(HttpUser):
    """Simula el flujo de navegación de un usuario en la aplicación."""

    wait_time = between(1.0, 3.0)

    def on_start(self) -> None:
        """Registra un usuario temporal y obtiene su token JWT."""
        self.email = f"loadtest_{uuid4().hex[:8]}@example.com"
        self.password = "LoadTestPassword123!"
        self.token = ""

        # Registro
        reg_res = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": self.email,
                "password": self.password,
                "full_name": "Locust Tester",
                "timezone": "America/Mexico_City",
            },
        )
        if reg_res.status_code == 201:
            # Login
            login_res = self.client.post(
                "/api/v1/auth/login",
                json={"email": self.email, "password": self.password},
            )
            if login_res.status_code == 200:
                self.token = login_res.json().get("access_token", "")

    @property
    def auth_headers(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    @task(3)
    def check_health(self) -> None:
        """Valida que los endpoints de salud respondan en p95 < 50ms."""
        self.client.get("/health/ready")

    @task(5)
    def browse_recipes(self) -> None:
        """Lectura pública del catálogo maestro de recetas."""
        self.client.get("/api/v1/recipes?limit=20")

    @task(4)
    def get_recommended_recipes(self) -> None:
        """Cálculo dinámico de recetas recomendadas personalizadas."""
        if self.token:
            self.client.get("/api/v1/recipes/recommended", headers=self.auth_headers)

    @task(3)
    def browse_pantries(self) -> None:
        """Consulta de despensas activas del usuario."""
        if self.token:
            self.client.get("/api/v1/pantries", headers=self.auth_headers)

    @task(2)
    def check_notifications(self) -> None:
        """Consulta de notificaciones in-app y conteo de no leídas."""
        if self.token:
            self.client.get("/api/v1/notifications", headers=self.auth_headers)


class OfflineOutboxUser(HttpUser):
    """Simula la outbox offline del frontend: reenvía cada consumo con la misma clave.

    Verifica bajo carga que los reintentos con la misma `Idempotency-Key` no repiten el
    descuento (issue #11). Cada consumo se envía tres veces: el original y dos reintentos.
    """

    wait_time = between(0.5, 1.5)
    retries_per_operation = 2

    def on_start(self) -> None:
        """Crea usuario, despensa, producto y un lote con stock de sobra."""
        self.headers: dict[str, str] = {}
        self.consume_url = ""
        self.product_id = ""
        email = f"outbox_{uuid4().hex[:8]}@example.com"
        password = "LoadTestPassword123!"
        reg = self.client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "Outbox Tester"},
        )
        login = self.client.post("/api/v1/auth/login", json={"email": email, "password": password})
        if reg.status_code != 201 or login.status_code != 200:
            return
        self.headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        pantry_id = self.client.post(
            "/api/v1/pantries", json={"name": "Carga"}, headers=self.headers
        ).json()["id"]
        location_id = self.client.get(
            f"/api/v1/pantries/{pantry_id}/locations", headers=self.headers
        ).json()[0]["id"]
        category_id = self.client.get("/api/v1/categories", headers=self.headers).json()[0]["id"]
        self.product_id = self.client.post(
            "/api/v1/products",
            json={
                "category_id": category_id,
                "name": f"Arroz {uuid4().hex[:6]}",
                "base_unit_code": "g",
            },
            headers=self.headers,
        ).json()["id"]
        self.client.post(
            f"/api/v1/pantries/{pantry_id}/batches",
            json={
                "location_id": location_id,
                "product_id": self.product_id,
                "unit_code": "g",
                "quantity": 1_000_000,
                "expiration_date": "2099-12-31",
            },
            headers=self.headers,
        )
        self.consume_url = f"/api/v1/pantries/{pantry_id}/consume"

    @task
    def consume_with_retries(self) -> None:
        """Consumo original + reintentos con la misma clave: el stock baja una sola vez."""
        if not self.consume_url:
            return
        headers = {**self.headers, "Idempotency-Key": str(uuid4())}
        body = {"product_id": self.product_id, "quantity": 1}

        original = self.client.post(self.consume_url, json=body, headers=headers, name="consume")
        for _ in range(self.retries_per_operation):
            with self.client.post(
                self.consume_url,
                json=body,
                headers=headers,
                name="consume (reintento idempotente)",
                catch_response=True,
            ) as retry:
                if retry.status_code == 409:
                    retry.success()  # la original sigue en curso: transitorio para la outbox
                elif retry.headers.get("Idempotent-Replayed") != "true":
                    retry.failure("El reintento se ejecutó de nuevo (sin Idempotent-Replayed)")
                elif retry.json() != original.json():
                    retry.failure("El reintento devolvió una respuesta distinta a la original")
