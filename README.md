# Bravo Backend

Backend de Bravo basado en Django, Django REST Framework y Channels. El proyecto expone API REST, documentacion OpenAPI/Swagger y endpoints WebSocket para chat de jobs y busqueda de organizaciones.

## Workflow

[Workflow Guide](docs/workflow.md)

## Stack

- Django 5
- Django REST Framework
- Channels
- Simple JWT
- drf-spectacular
- PostgreSQL
- LocalStack para S3/SES en desarrollo

## Estructura relevante

- `Core/`: configuracion Django/ASGI/URLs globales
- `docs/`: documentacion tecnica y OpenAPI exportada

## Requisitos

- Docker
- Docker Compose con `docker compose`

## Arranque local

Servicios definidos en `compose.yml`:

- `nginx`: proxy inverso de entrada
- `app`: backend Django
- `postgres`: base de datos principal
- `adminer`: interfaz web para inspección manual de PostgreSQL
- `localstack`: emulacion local de S3/SES
- `db-diagram-exporter`: exportacion del esquema de base de datos

El backend queda expuesto directamente en `http://localhost:8000` y también a través de `nginx` en `http://localhost:24356`.
Las peticiones `http://localhost:24356/s3/...` se enrutan a `localstack`.
PostgreSQL queda accesible desde el host en `localhost:5432` o en el puerto definido por `POSTGRES_PORT`.
La base de datos puede inspeccionarse en `http://localhost:24357` con servidor `postgres` y las credenciales de `POSTGRES_USER`/`POSTGRES_PASSWORD`.

## Endpoints principales

Base URL REST: `http://localhost:8000/api/` o `http://localhost:24356/api/`

Rutas registradas:

- `api/auth/`
- `api/organizations/`
- `api/jobs/`
- `api/management/`
- `api/rgpd/`

Infraestructura general:

- `GET /health/`
- `GET /api/schema/`
- `GET /api/docs/` (Swagger UI)
- `GET /admin/`

## WebSockets

Rutas ASGI expuestas:

- `ws/chats/<chat_uuid>/`
- `ws/organization/search/`

Notas:

- Los sockets usan autenticacion JWT por cabecera `Authorization: Bearer <access_token>`.
- La busqueda de organizaciones tiene cobertura de tests especifica en la app `organization`.
- El contrato del socket de busqueda de organizaciones esta documentado en `docs/ws-organization-search.md`.
- El esquema OpenAPI de `drf-spectacular` documenta solo endpoints HTTP, no contratos WebSocket.

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

## Documentacion adicional

- `docs/README.md` (índice canónico de documentación)
- `docs/setup-dev-env.md`
- `docs/environment-variables.md`
- `docs/workflow.md`
- `http://localhost:24356/api/docs/` para navegar el Swagger UI en local
