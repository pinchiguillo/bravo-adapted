# Getting Started

Guía paso a paso para arrancar el entorno de desarrollo e integración.

## Requisitos

- Docker
- Docker Compose (`docker compose` CLI)

## Inicio Rápido

### Opción 1: Script automatizado (recomendado)

```bash
cd backend/
./setup_dev.sh
```

El script realiza:
1. Copia `example.env` → `.env` (si no existe)
2. Levanta stack: `docker compose up -d --build`
3. Espera healthchecks
4. Ejecuta tests
5. Pregunta si ejecutar seeds

### Opción 2: Manual paso a paso

```bash
cd backend/
cp example.env .env
docker compose -f compose.yml up --build
```

Backend disponible en `http://localhost:8000`

## Primeros Pasos

### Acceder a la API

```bash
# Documentación Swagger
http://localhost:8000/api/docs/

# Schema OpenAPI
http://localhost:8000/api/schema/

# Health check
curl http://localhost:8000/health/
```

### Ejecutar tests

```bash
docker compose -f compose.yml exec -T app python manage.py test
```

O un test específico:

```bash
docker compose -f compose.yml exec -T app python manage.py test \
  apps.organization.tests.OrganizationSearchTestCase
```

### Lint y formato

```bash
# Revisar
docker compose -f compose.yml exec -T app ruff check --config .github/ruff.toml Core apps manage.py

# Autofijar
docker compose -f compose.yml exec -T app ruff check --fix --config .github/ruff.toml Core apps manage.py
```

### Migraciones de base de datos

```bash
# Generar migraciones
docker compose -f compose.yml exec -T app python manage.py makemigrations

# Aplicar
docker compose -f compose.yml exec -T app python manage.py migrate

# Ver estado
docker compose -f compose.yml exec -T app python manage.py showmigrations
```

### Acceso a PostgreSQL

Desde cliente local:
- **Host**: `127.0.0.1`
- **Puerto**: `5432`
- **DB**: `auth_db`
- **User**: `postgres`
- **Password**: `postgres`

O web (Adminer):
```
http://localhost:24357
```

## Comandos Útiles Diarios

```bash
# Estado de servicios
docker compose -f compose.yml ps

# Logs de app
docker compose -f compose.yml logs -f app

# Entrar a terminal de app
docker compose -f compose.yml exec app bash

# Detener stack
docker compose -f compose.yml down

# Detener y limpiar volúmenes
docker compose -f compose.yml down -v

# Rebuild sin cache
docker compose -f compose.yml build --no-cache
```

## Troubleshooting Rápido

### Error: Database connection refused

```bash
# Verificar que postgres está corriendo
docker compose -f compose.yml logs postgres

# Reconstruir postgres
docker compose -f compose.yml down -v
docker compose -f compose.yml up --build
```

### Error: ModuleNotFoundError en imports

```bash
# Reinstalar dependencias
docker compose -f compose.yml build --no-cache
docker compose -f compose.yml up
```

### Lint falla en CI

```bash
# Autofijar localmente
docker compose -f compose.yml exec -T app ruff check --fix --config .github/ruff.toml Core apps manage.py
```

### LocalStack no funciona

```bash
# Revisar logs
docker compose -f compose.yml logs localstack

# Verificar salud
docker compose -f compose.yml exec -T localstack \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:4566/_localstack/health', timeout=5).read().decode())"
```

## Configuración del Entorno

### Variables clave en `.env`

```env
APP_MODE=development              # development o production
DEBUG=1                           # 1 en desarrollo, 0 en producción
SECRET_KEY=dev-key-insecure       # >50 caracteres en producción
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/auth_db

# Storage S3 (LocalStack en dev)
USE_S3_STORAGE=1
AWS_STORAGE_BUCKET_NAME=bravo-bucket
MEDIA_PUBLIC_BASE_URL=/s3

# Email (SES en LocalStack)
USE_SES_EMAIL=1
DEFAULT_FROM_EMAIL=noreply@bravo.local

# Auth
AUTH_BYPASS_EMAIL_VERIFICATION=1  # 1 en desarrollo
```

Ver [ENVIRONMENT.md](./ENVIRONMENT.md) para todas las variables disponibles.

## Stack de Servicios

En `compose.yml`:
- **app**: Django (puerto 8000)
- **postgres**: PostgreSQL (puerto 5432, interno)
- **localstack**: S3 + SES simulados (puerto 4566, interno)
- **nginx**: Proxy local (puerto 24356 público)
- **adminer**: Web DB browser (puerto 24357 público)
- **db-diagram-exporter**: Diagrama de schema (opcional)

## Documentación Relacionada

- [ENVIRONMENT.md](./ENVIRONMENT.md) — Variables de entorno completas
- [OPERATIONS.md](./OPERATIONS.md) — Troubleshooting y producción
- [ARCHITECTURE.md](./ARCHITECTURE.md) — Visión general del sistema
- [WORKFLOW.md](./WORKFLOW.md) — Ramas, CI/CD, versionado
