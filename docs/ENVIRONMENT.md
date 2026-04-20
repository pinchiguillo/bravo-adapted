# Environment Variables

Referencia completa de variables de entorno leídas desde `.env` por `Core/settings.py`.

## Arranque Rápido

Copiar `example.env` a `.env`:

```bash
cp example.env .env
```

Las variables sin definir usan valores por defecto. En **producción** se exigen varios (ver sección).

## Categorías

### Mode & Debug

- **`APP_MODE`**: `development` o `production`
  - Default: `development` en `compose.yml`, `production` en `compose.prod.yml`
  - En producción endurecen validaciones
- **`DEBUG`**: `1` o `0`
  - Default: `1` (desarrollo), `0` (producción)
  - En producción es forzado a `0`
- **`PORT`**: puerto de escucha
  - Default: `8000`

### Django Security (requeridos en producción)

- **`SECRET_KEY`** (REQUERIDO en prod): clave secreta Django, >50 caracteres
- **`ALLOWED_HOSTS`**: hosts permitidos, separados por comas
  - Default: `localhost,127.0.0.1`
  - Ejemplo: `api.example.com,api-staging.example.com`
- **`CSRF_TRUSTED_ORIGINS`**: orígenes confiables, separados por comas
  - Formato: `https://dominio.com`

### HTTP Security (requeridos en producción)

- **`SECURE_SSL_REDIRECT`**: redirigir HTTP → HTTPS
  - Default: `True` (producción), `False` (desarrollo)
- **`SECURE_HSTS_SECONDS`**: HSTS max-age en segundos
  - Default: `31536000` (1 año)
- **`SECURE_HSTS_INCLUDE_SUBDOMAINS`**: HSTS incluye subdomains
  - Default: `True`
- **`SECURE_HSTS_PRELOAD`**: permitir preload HSTS
  - Default: `False`
- **`SESSION_COOKIE_SECURE`**: cookies solo por HTTPS
  - Default: `True` (producción), `False` (desarrollo)
- **`CSRF_COOKIE_SECURE`**: CSRF cookie solo por HTTPS
  - Default: `True` (producción), `False` (desarrollo)
- **`SECURE_PROXY_SSL_HEADER`**: header para detectar SSL en proxy
  - Formato: `HEADER_NAME,header_value`
  - Ejemplo: `HTTP_X_FORWARDED_PROTO,https`

### CORS

- **CORS en desarrollo**: `CORS_ALLOW_ALL_ORIGINS=True` (automático)
- **CORS en producción**: desactivado (debe configurar `CSRF_TRUSTED_ORIGINS`)

### Database (requerido en Docker/producción)

- **`DATABASE_URL`** (REQUERIDO en prod): conexión PostgreSQL
  - Ejemplo: `postgresql://user:pass@host:5432/dbname`
  - Fallback local (sin Docker): SQLite

### Cache & Canales

- **`REDIS_URL`** (REQUERIDO en prod): conexión Redis para channel layer
  - Ejemplo: `redis://localhost:6379/0`
  - Desarrollo: fallback a `InMemoryChannelLayer` si no existe

### AWS & Storage (requerido si `USE_S3_STORAGE=1`)

- **`AWS_DEFAULT_REGION`**: región AWS
  - Default: `us-east-1`
- **`AWS_ACCESS_KEY_ID`**: access key
- **`AWS_SECRET_ACCESS_KEY`**: secret key
- **`AWS_S3_ENDPOINT_URL`**: endpoint S3
  - Default: `http://localstack:4566` (desarrollo)
  - Producción: S3 real o compatible
- **`AWS_STORAGE_BUCKET_NAME`** (REQUERIDO): bucket S3
  - Default: `bravo-bucket`
- **`AWS_SES_ENDPOINT_URL`**: endpoint SES (si `USE_SES_EMAIL=1`)
  - Default: `http://localstack:4566` (desarrollo)
- **`MEDIA_PUBLIC_BASE_URL`**: base pública para URLs de media
  - Default: `/s3`
  - Desarrollo: `nginx` proxy hacia LocalStack en `/s3/*`
- **`USE_S3_STORAGE`** (REQUERIDO): habilitar S3
  - Default: `1`
  - Si es `0`, falla en startup con `ImproperlyConfigured`
- **`USE_SES_EMAIL`**: usar SES para emails
  - Default: `1` (desarrollo con LocalStack)
- **`DEFAULT_FROM_EMAIL`**: remitente de emails
  - Default: `noreply@bravo.local`

### Email (SMTP alternativo)

Si `USE_SES_EMAIL=0`, se usa SMTP:

- **`EMAIL_BACKEND`**: backend de email (default: `django.core.mail.backends.console.EmailBackend` en dev)
- **`EMAIL_HOST`**: servidor SMTP
- **`EMAIL_PORT`**: puerto SMTP
- **`EMAIL_HOST_USER`**: usuario SMTP
- **`EMAIL_HOST_PASSWORD`**: contraseña SMTP
- **`EMAIL_USE_TLS`**: `1` o `0`
- **`EMAIL_USE_SSL`**: `1` o `0`

### Auth & JWT

- **`AUTH_VERIFY_EMAIL_URL_TEMPLATE`**: URL para verificar email
  - Ejemplo: `https://app.example.com/verify?token={token}`
- **`AUTH_BYPASS_EMAIL_VERIFICATION`**: omitir verificación email
  - Default: `1` (desarrollo), `0` (producción forzado)
- **`BYPASS_ADMIN_LOGIN`**: no requerir autenticación en `api/management/`
  - Default: `0`
  - Forzado a `0` en producción
- **`BYPASS_ORGANIZATION_VALIDATION`**: organizaciones auto-validadas
  - Default: `0`
- **`AUTH_ENFORCE_PASSWORD_RESTRICTIONS`**: validar complejidad de password
  - Default: `1`
  - Si es `0`, permite passwords sin restricciones (desarrollo)
- **`JWT_ROTATE_REFRESH_TOKENS`**: rotar tokens al refrescar
  - Default: `1`
- **`HIDE_API_DOCS`**: ocultar Swagger UI y schema
  - Default: `0` (desarrollo), `1` (producción)

### Jobs & Job Chat

- **`JOB_CHAT_ATTACHMENT_MAX_BYTES`**: tamaño máximo de adjuntos
  - Default: `5242880` (5MB)
- **`JOB_CHAT_ATTACHMENT_ALLOWED_CONTENT_TYPES`**: MIME types permitidos, separados por comas
  - Default: `image/jpeg,image/png,image/gif,application/pdf`
- **`JOB_CHAT_WS_RATE_LIMIT`**: máximo de mensajes por ventana
  - Default: `100`
- **`JOB_CHAT_WS_RATE_WINDOW`**: ventana de rate limit en segundos
  - Default: `60`
- **`JOB_CHAT_ATTACHMENT_URL_TTL_SECONDS`**: expiración de URLs firmadas
  - Default: `3600` (1 hora)

### Rate Limiting (DRF Throttling)

Formato: `N/M` donde N=requests, M=timeframe (e.g., `10/hour`)

- **`AUTH_DEFAULT_THROTTLE_RATE`**: por defecto
  - Default: `10/minute`
- **`AUTH_LOGIN_THROTTLE_RATE`**: login
  - Default: `5/minute`
- **`AUTH_REGISTER_THROTTLE_RATE`**: registro
  - Default: `3/minute`
- **`AUTH_REFRESH_THROTTLE_RATE`**: refresh token
  - Default: `10/minute`
- **`AUTH_VERIFY_EMAIL_THROTTLE_RATE`**: verificar email
  - Default: `5/minute`
- **`ORGANIZATION_DEFAULT_THROTTLE_RATE`**: org por defecto
  - Default: `20/minute`
- **`ORGANIZATION_PUBLIC_READ_THROTTLE_RATE`**: lectura pública
  - Default: `100/minute`
- **`ORGANIZATION_AUTHENTICATED_READ_THROTTLE_RATE`**: lectura autenticada
  - Default: `50/minute`
- **`ORGANIZATION_WRITE_THROTTLE_RATE`**: escritura
  - Default: `10/minute`
- **`ORGANIZATION_ADMIN_THROTTLE_RATE`**: admin
  - Default: `100/minute`
- **`JOBS_DEFAULT_THROTTLE_RATE`**: jobs por defecto
  - Default: `20/minute`
- **`JOBS_READ_THROTTLE_RATE`**: lectura jobs
  - Default: `50/minute`
- **`JOBS_WRITE_THROTTLE_RATE`**: escritura jobs
  - Default: `10/minute`
- **`JOBS_MESSAGES_THROTTLE_RATE`**: mensajes jobs
  - Default: `20/minute`
- **`JOBS_ATTACHMENTS_THROTTLE_RATE`**: adjuntos jobs
  - Default: `10/minute`

### PostgreSQL Container (solo Docker)

- **`POSTGRES_DB`**: nombre de base de datos
  - Default: `auth_db`
- **`POSTGRES_USER`**: usuario PostgreSQL
  - Default: `postgres`
- **`POSTGRES_PASSWORD`**: contraseña PostgreSQL
  - Default: `postgres`
- **`POSTGRES_PORT`**: puerto expuesto
  - Default: `5432`

### Túnel Cloudflare (opcional)

- **`CLOUDFLARED_TUNNEL_TOKEN`**: token del túnel Cloudflare
  - Si se proporciona y se usa `--profile cloudflared`, expone backend públicamente

## Checklist para Producción

- [ ] `APP_MODE=production`
- [ ] `DEBUG=0`
- [ ] `SECRET_KEY` > 50 caracteres
- [ ] `ALLOWED_HOSTS` configurado
- [ ] `CSRF_TRUSTED_ORIGINS` configurado
- [ ] `DATABASE_URL` apuntando a PostgreSQL externo
- [ ] `REDIS_URL` apuntando a Redis externo
- [ ] `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY` válidas
- [ ] `AWS_STORAGE_BUCKET_NAME` existe en S3
- [ ] `USE_S3_STORAGE=1`
- [ ] `SECURE_SSL_REDIRECT=True`
- [ ] `SESSION_COOKIE_SECURE=True`
- [ ] `CSRF_COOKIE_SECURE=True`
- [ ] `HIDE_API_DOCS=1` (opcional pero recomendado)

Validar con:

```bash
python manage.py check --deploy
```

## Referencia Rápida

Valores por defecto en `example.env`:

```env
APP_MODE=
DEBUG=1
SECRET_KEY=dev-insecure-key
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/auth_db
REDIS_URL=
USE_S3_STORAGE=1
AWS_STORAGE_BUCKET_NAME=bravo-bucket
DEFAULT_FROM_EMAIL=noreply@bravo.local
AUTH_BYPASS_EMAIL_VERIFICATION=1
```

## Documentación Relacionada

- [GETTING_STARTED.md](./GETTING_STARTED.md) — Setup inicial
- [ARCHITECTURE.md](./ARCHITECTURE.md) — Visión general
- [OPERATIONS.md](./OPERATIONS.md) — Troubleshooting
