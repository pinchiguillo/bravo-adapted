# Setup del entorno de desarrollo

## Requisitos

- Docker
- Docker Compose con `docker compose`

## Arranque inicial

Trabajando desde `backend/`:

```bash
cp example.env .env
docker compose -f compose.yml up --build
```

El backend queda disponible en `http://localhost:8000`.

## Servicios del entorno local

- `app`: aplicacion Django
- `postgres`: base de datos PostgreSQL
- `localstack`: servicios AWS locales para S3 y SES
- `db-diagram-exporter`: utilidad para exportar el esquema de base de datos

## Comandos utiles

```bash
# Levantar el entorno
docker compose -f compose.yml up --build

# Ejecutar tests
docker compose -f compose.yml exec -T app python manage.py test

# Lint
docker compose -f compose.yml exec -T app ruff check Core auth organization jobs management rgpd manage.py

# Generar migraciones
docker compose -f compose.yml exec -T app python manage.py makemigrations

# Verificar que no falten migraciones
docker compose -f compose.yml exec -T app python manage.py makemigrations --check --dry-run

# Checks de despliegue en modo produccion
docker compose -f compose.yml exec -T app env \
  APP_MODE=production \
  DEBUG=0 \
  ALLOWED_HOSTS=api.example.com \
  CSRF_TRUSTED_ORIGINS=https://api.example.com \
  SECRET_KEY=production-secret-key-with-enough-entropy-1234567890 \
  python manage.py check --deploy
```

## Documentacion API

- Swagger UI local: `http://localhost:8000/api/docs/`
- OpenAPI schema: `http://localhost:8000/api/schema/`
- Export estatico: `docs/swagger.html`
- Export OpenAPI: `docs/swagger.yaml`
