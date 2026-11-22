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
