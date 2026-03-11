# Estructura recomendada del repositorio (`backend`)

Este documento asume que **`backend/` es la raíz del repositorio en GitHub**.

## 1) Estructura recomendada

```text
.
├── .github/
│   └── workflows/
│       ├── backend-ci.yml
│       └── backend-cd.yml
├── Core/
├── auth/
├── organization/
├── jobs/
├── rgpd/
├── management/
├── docs/
│   ├── arquitectura.md
│   ├── entorno-desarrollo.md
│   ├── operacion.md
│   └── devreports/
├── docker/
├── compose.yml
├── compose.prod.yml
├── Dockerfile
├── Dockerfile.prod
├── entrypoint.sh
├── manage.py
├── requirements.txt
└── ruff.toml
```

Criterios:
- `Core/` contiene settings, urls globales, ASGI/WSGI.
- Cada app Django mantiene su `urls.py`, `views.py`, `serializers.py`, `models.py` y tests.
- `docs/devreports/` guarda un reporte breve por cambio funcional/técnico.
- Workflows CI/CD en `.github/workflows/`.

## 2) Modelo de ramas recomendado

- `main` (o `master`): rama protegida de integración estable.
- `develop` (opcional): integración previa cuando haya alta concurrencia de cambios.
- Ramas de trabajo desde `main` o `develop`:
  - `feature/<descripcion-corta>`
  - `fix/<descripcion-corta>`
  - `hotfix/<descripcion-corta>`
  - `chore/<descripcion-corta>`

Reglas recomendadas:
- No hacer push directo a `main/master`.
- Todo cambio entra por Pull Request.
- PRs pequeñas y atómicas (menor riesgo de regresión).

## 3) Validaciones obligatorias antes de merge

## 3.1 CI en verde (requisito bloqueante)

El workflow de CI debe pasar completo:
- build de imagen `app`
- tests Django
- lint `ruff`
- `manage.py check --deploy` con variables de producción

Comandos equivalentes locales (desde la raíz del repo `backend`):

```bash
cp example.env .env

docker compose -f compose.yml build app

docker compose -f compose.yml up -d postgres localstack

docker compose -f compose.yml run --rm app python manage.py test

docker compose -f compose.yml run --rm --no-deps \
  -e APP_MODE=production \
  -e DEBUG=0 \
  -e ALLOWED_HOSTS=api.example.com \
  -e CSRF_TRUSTED_ORIGINS=https://api.example.com \
  -e SECRET_KEY=production-secret-key-with-enough-entropy-1234567890 \
  app python manage.py check --deploy

docker compose -f compose.yml run --rm --no-deps app \
  ruff check Core auth organization jobs manage.py

docker compose -f compose.yml down -v --remove-orphans
```

## 3.2 Requisitos de calidad del PR

Antes de merge:
- PR con descripción clara (contexto, alcance, riesgos).
- Tests acordes al cambio (nuevos o actualizados).
- Migraciones generadas con Django si hubo cambios de modelo.
- Confirmar `makemigrations --check --dry-run` cuando aplique.
- Reporte en `docs/devreports/` con:
  - contexto,
  - cambios aplicados,
  - tests/validaciones ejecutadas,
  - pendientes si existen.

## 3.3 Protección recomendada de rama `main/master`

Configurar en GitHub:
- `Require a pull request before merging`.
- `Require status checks to pass before merging`:
  - `Backend CI / backend`
- `Require branches to be up to date before merging`.
- `Require conversation resolution before merging`.
- `Require at least 1 approval`.
- `Do not allow bypassing the above settings` (salvo administradores si política interna lo exige).

## 4) CD (después del merge)

El workflow `backend-cd.yml` publica imagen en GHCR cuando:
- CI termina exitoso en `main/master`, o
- se ejecuta manualmente (`workflow_dispatch`).

Resultado esperado:
- imagen `ghcr.io/<owner>/bravo-backend`
- tags: `latest` (rama por defecto), `sha-*`, y tags Git.

## 5) Checklist operativo de merge

1. CI en verde en la PR.
2. Cambios revisados y aprobados.
3. Tests y migraciones validadas.
4. `docs/devreports/` actualizado.
5. Merge por método acordado (recomendado `squash merge` para historial limpio).
