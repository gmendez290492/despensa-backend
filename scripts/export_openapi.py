"""Exporta el esquema OpenAPI (Swagger) del backend a docs/openapi.json."""

import json
from pathlib import Path

from app.main import create_app


def export_openapi() -> None:
    app = create_app()
    openapi_schema = app.openapi()

    output_dir = Path("docs")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "openapi.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)

    print(f"Esquema OpenAPI exportado exitosamente en: {output_file}")


if __name__ == "__main__":
    export_openapi()
