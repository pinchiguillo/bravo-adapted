# Operations

Guía de troubleshooting, monitoreo y despliegue en producción.

## Comprobaciones Rápidas

### Estado de Servicios

```bash
docker compose -f compose.yml ps
```

Esperado:
- `app` — running (depends on postgres, localstack)
- `postgres` — healthy
- `localstack` — healthy

### Logs en Tiempo Real

```bash
docker compose -f compose.yml logs -f app
```

O filtrar por servicio específico:

```bash
docker compose -f compose.yml logs -f postgres
docker compose -f compose.yml logs -f localstack
```

### Health Endpoints

```bash
curl http://localhost:8000/health/
```

Respuesta: `{"status": "ok"}`

### Verificar Base de Datos

```bash
docker compose -f compose.yml run --rm --no-deps app \
  python manage.py showmigrations
```

Todas las migraciones deben mostrar estado `[X]` (aplicadas).

## Troubleshooting Común

### Error: Connection refused (database)

**Síntomas**: `Error connecting to PostgreSQL`, `(2003) Can't connect to MySQL server`

**Causas posibles**:
1. PostgreSQL no está corriendo
2. `DATABASE_URL` incorrea
3. Credenciales inválidas

**Solución**:

```bash
# Verificar logs
docker compose -f compose.yml logs postgres

# Reconstruir sin cache
docker compose -f compose.yml down -v
docker compose -f compose.yml up --build
```

### Error: ModuleNotFoundError

**Síntomas**: `ModuleNotFoundError: No module named 'apps.organization'`

**Causas**: Dependencias no instaladas, cambios en `requirements.txt` sin rebuild

**Solución**:

```bash
docker compose -f compose.yml build --no-cache
docker compose -f compose.yml up
```

### Falla en tests

**Síntomas**: `ERROR: ... test ...`

**Verificar**:

```bash
# Ejecutar tests localmente
docker compose -f compose.yml exec -T app python manage.py test

# Test específico
docker compose -f compose.yml exec -T app python manage.py test apps.auth.tests
```

**Revisar DB migrations**:

```bash
docker compose -f compose.yml exec -T app python manage.py makemigrations --check --dry-run
```

### Lint falla (Ruff)

**Síntomas**: `ERROR [E501] Line too long`

**Solución automática**:

```bash
docker compose -f compose.yml exec -T app \
  ruff check --fix --config .github/ruff.toml Core apps manage.py
```

Luego commitar cambios.

### Email no envía (SES)

**Síntomas**: Emails no llegan, error de verificación en LocalStack

**Verificar identidades SES**:

```bash
docker compose -f compose.yml exec -T localstack awslocal ses list-identities
```

**Crear identidad manualmente**:

```bash
docker compose -f compose.yml exec -T localstack \
  awslocal ses verify-email-identity --email-address test@example.com
```

**Verificar `DEFAULT_FROM_EMAIL` en `.env`**:

```bash
# Debe coincidir con una identidad verificada
DEFAULT_FROM_EMAIL=noreply@bravo.local
```

### LocalStack no funciona

**Síntomas**: Error al subir archivos S3, `403 Forbidden`

**Verificar salud**:

```bash
docker compose -f compose.yml exec -T localstack \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:4566/_localstack/health', timeout=5).read().decode())"
```

**Revisar logs**:

```bash
docker compose -f compose.yml logs localstack
```

**Reconstruir bucket**:

```bash
docker compose -f compose.yml down -v
docker compose -f compose.yml up --build
```

### Redis no disponible

**Síntomas**: WebSocket no funciona, `ChannelLayerUnavailable`

**Desarrollo**: si no existe `REDIS_URL`, usa `InMemoryChannelLayer` (OK con un proceso).

**Producción**: `REDIS_URL` es obligatorio. Verificar:

```bash
docker compose -f compose.yml logs redis
```

### PostgreSQL: acceso desde host

```bash
# Usando psql
psql -h 127.0.0.1 -U postgres -d auth_db

# Usando web (Adminer)
http://localhost:24357
```

Credenciales:
- Host: `postgres`
- Usuario: `postgres`
- Password: `postgres`
- DB: `auth_db`

### Acceso web a LocalStack

S3 buckets en `http://localhost:24356/s3/`

## Producción

### Arrancador Stack Productivo

```bash
cd backend/
docker compose -f compose.prod.yml up --build -d
```

Servicios levantados:
- `nginx` — reverse proxy (puerto 80/443 público)
- `app` — Django Daphne (interno)
- `postgres` — database (interno)
- `redis` — channel layer (interno)
- `localstack` — S3/SES (opcional, normalmente S3 real)

### Health Check

```bash
curl http://localhost:8000/health/
```

### Logs

```bash
docker compose -f compose.prod.yml logs -f app
```

### Actualizar Código

```bash
git pull
docker compose -f compose.prod.yml build --no-cache
docker compose -f compose.prod.yml up -d
```

Docker Compose ejecuta migraciones automáticamente via `entrypoint.sh`.

### Monitoreo Básico

**Conexiones activas PostgreSQL**:

```bash
docker compose -f compose.prod.yml exec postgres \
  psql -U postgres -d auth_db -c "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;"
```

**Tamaño DB**:

```bash
docker compose -f compose.prod.yml exec postgres \
  psql -U postgres -d auth_db -c "SELECT pg_size_pretty(pg_database_size('auth_db'));"
```

**Tamaño bucket S3**:

```bash
# Si usa LocalStack
docker compose -f compose.prod.yml exec localstack \
  awslocal s3 ls s3://bravo-bucket --recursive --human-readable --summarize
```

### Cloudflare Tunnel (Opcional)

```bash
docker compose -f compose.prod.yml --profile cloudflared up --build -d
```

Requiere token en `.env`:

```env
CLOUDFLARED_TUNNEL_TOKEN=...
```

## Checks Pre-Deploy

Antes de subir a producción:

```bash
# 1. Lint
docker compose -f compose.yml exec -T app \
  ruff check --config .github/ruff.toml Core apps manage.py

# 2. Tests
docker compose -f compose.yml exec -T app python manage.py test

# 3. Migraciones sin cambios no commiteados
docker compose -f compose.yml exec -T app \
  python manage.py makemigrations --check --dry-run

# 4. Check deploy (con variables producción)
docker compose -f compose.yml run --rm --no-deps -e \
  APP_MODE=production -e DEBUG=0 -e SECRET_KEY=test-secret-key-with-enough-entropy \
  -e ALLOWED_HOSTS=api.example.com -e CSRF_TRUSTED_ORIGINS=https://api.example.com \
  app python manage.py check --deploy
```

## Limpieza y Mantenimiento

### Limpiar volúmenes (destruye datos)

```bash
docker compose -f compose.yml down -v
```

### Prune de imágenes no usadas

```bash
docker image prune -a -f
```

### Backup de base de datos

```bash
docker compose -f compose.yml exec postgres \
  pg_dump -U postgres auth_db > backup.sql
```

### Restaurar base de datos

```bash
docker compose -f compose.yml exec -T postgres \
  psql -U postgres auth_db < backup.sql
```

## Reglas Operativas

- **Nunca ejecutes Python/Django en el host**. Siempre usa `docker compose exec app` o `docker run`.
- **Ejecuta migraciones en el entrypoint**, no manualmente después de deploy.
- **Usa volúmenes nombrados** para datos persistentes, no directorios del host.
- **Monitorea logs** en tiempo real durante cambios.
- **Backupea antes de operaciones destructivas** (`down -v`).

## Documentación Relacionada

- [GETTING_STARTED.md](./GETTING_STARTED.md) — Setup inicial
- [ARCHITECTURE.md](./ARCHITECTURE.md) — Visión general
- [ENVIRONMENT.md](./ENVIRONMENT.md) — Variables de entorno
- [WORKFLOW.md](./WORKFLOW.md) — CI/CD y ramas
