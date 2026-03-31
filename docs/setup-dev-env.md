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

`example.env` no define `APP_MODE`; en local lo resuelve `compose.yml` con default `development`.

También puedes usar el script de bootstrap:

```bash
./setup_dev.sh
```

El script realiza este flujo:

1. Copia `example.env` a `.env` solo si `.env` no existe.
2. Levanta el stack completo (`docker compose up -d --build`).
3. Espera a que `app` esté healthy.
4. Ejecuta `python manage.py test`.
5. Pregunta si se desean ejecutar seeds de base de datos (`seed_demo_data` y `create_admin_user`).

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
docker compose -f compose.yml exec -T app ruff check --config .github/ruff.toml Core apps manage.py

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
