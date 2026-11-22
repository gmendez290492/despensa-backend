## Descripción del cambio
<!-- Explica brevemente qué resuelve este Pull Request y a qué etapa pertenece -->

## Flujo Gitflow
- [ ] Esta rama parte de `develop` (para `feature/*`) o sigue el flujo de `release/*` / `hotfix/*` hacia `main`.
- [ ] El título del PR sigue Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`).

## Checklist de Calidad y Seguridad
- [ ] `ruff check .` y `ruff format --check .` pasan sin errores.
- [ ] `mypy src` pasa sin errores de tipado.
- [ ] `bandit -c pyproject.toml -r src` sin hallazgos de seguridad.
- [ ] Pruebas unitarias y de integración (`pytest`) actualizadas y pasando.
- [ ] Si hubo cambios en modelos ORM, se incluyó la migración de Alembic (`alembic upgrade head`).
- [ ] Ningún secreto, token o contraseña real fue incluido en el código.
