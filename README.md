# Bravo Backend

Backend de Bravo basado en Django, Django REST Framework y Channels. El proyecto expone API REST, documentacion OpenAPI/Swagger y endpoints WebSocket para chat de jobs y busqueda de organizaciones.

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

- `app`: backend Django
- `postgres`: base de datos principal
- `localstack`: emulacion local de S3/SES
- `db-diagram-exporter`: exportacion del esquema de base de datos

El backend queda expuesto en `http://localhost:8000`.

## Endpoints principales

Base URL REST: `http://localhost:8000/api/`

Rutas registradas:

- `api/auth/`
- `api/organization/`
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

- `ws/jobs/<job_uuid>/chat/`
- `ws/organization/search/`

Notas:

- El chat de jobs usa autenticacion JWT en WebSocket mediante el middleware del proyecto.
- La busqueda de organizaciones tiene cobertura de tests especifica en la app `organization`.

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

## Documentacion adicional

- `docs/setup-dev-env.md`
- `docs/environment-variables.md`
- `docs/active-apps.md`
- `docs/arquitectura.md`
- `docs/entorno-desarrollo.md`
- `docs/operacion.md`
- `docs/swagger.yaml`
- `docs/swagger.html`
- `http://localhost:8000/api/docs/` para navegar el Swagger UI en local
