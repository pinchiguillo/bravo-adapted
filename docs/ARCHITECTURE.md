# Architecture

Visión general del sistema, componentes y decisiones técnicas.

## Visión General

Backend Django/DRF/Channels con arquitectura modular por dominios de negocio.

```
┌─────────────────┐
│   Clientes      │
│  (Web, Mobile)  │
└────────┬────────┘
         │ HTTP + WebSocket
    ┌────┴─────────────────────┐
    │    nginx (reverse proxy)  │
    └────┬─────────────────────┘
         │
    ┌────┴──────────────────────────┐
    │   Django ASGI (Daphne/Dev)    │
    │  - DRF REST API               │
    │  - Django Channels WebSocket  │
    └────┬──────────────────────────┘
         │
    ┌────┴──────────────────────────────┐
    │                                    │
┌───┴──────────────┐      ┌─────────────┴────┐
│   PostgreSQL     │      │   Redis (prod)   │
│   (data store)   │      │  (channel layer) │
└──────────────────┘      └──────────────────┘
         │
    ┌────┴─────────────────┐
    │    S3 / LocalStack   │
    │  (file storage)      │
    └──────────────────────┘
```

## Componentes Principales

### 1. Backend (Django)

**Runtime**: `python:3.12-slim`  
**Framework**: Django + Django REST Framework + Django Channels  
**Servidor**:
- Desarrollo: `python manage.py runserver 0.0.0.0:8000`
- Producción: `daphne -b 0.0.0.0 -p 8000 Core.asgi:application`

**Responsabilidades**:
- Ejecutar migraciones al arranque
- Cargar config desde `.env`
- Servir HTTP/REST/WebSocket en puerto 8000
- Gestionar autenticación JWT
- Orquestar acceso a storage y emails

### 2. Base de Datos

**PostgreSQL 16-alpine**  
- Usuario: `postgres`
- DB: `auth_db`
- Puerto interno: 5432 (no publicado)
- Persistencia: volumen Docker `postgres_data`

Healthcheck: `pg_isready -U postgres -d auth_db`

### 3. Channel Layer (Producción)

**Redis 7-alpine**  
- Rol: fan-out para WebSocket en multiproceso
- Conexión: variable `REDIS_URL`
- Desarrollo: fallback a `InMemoryChannelLayer` si no existe `REDIS_URL`
- Producción: requerido

### 4. Servicios AWS Locales

**LocalStack 3.8.1**  
Servicios simulados:
- **S3**: almacenamiento de archivos
- **SES**: envío de emails
- **SQS**, **SNS**: (instalados pero no usados actualmente)

Endpoint: `http://localhost:4566`  
Bootstrap: `docker/localstack/init/10-aws-bootstrap.sh`
- Crea bucket `AWS_STORAGE_BUCKET_NAME`
- Verifica identidad SES `DEFAULT_FROM_EMAIL`

### 5. Proxy Inverso (nginx)

**Desarrollo/Producción**  
Roles:
- Servir `/s3/*` → LocalStack (proxy para archivos)
- Balanceo (producción)
- Terminación SSL (producción)

Puerto público: `24356` (dev), `80/443` (prod)

## Estructura de Apps Django

```
apps/
├── auth/              # Autenticación (login, register, JWT)
├── organization/      # Organizaciones, anuncios, servicios
├── jobs/             # Contrataciones vinculadas a anuncios
├── job_chat/         # Chat en tiempo real por job
├── assets/           # Sistema centralizado de S3
├── management/       # Admin endpoints (staff/superuser)
└── rgpd/             # RGPD (condicional)

common/
├── permissions.py    # Permisos base
├── throttling.py     # Rate limiting
├── pagination.py     # Paginación
└── email.py          # Backends de email
```

### App `auth`

**Modelos**:
- `CustomUser`: usuario con avatar, email verificado, estado activo

**Endpoints** (`api/auth/`):
- `POST /register/` — crear cuenta
- `POST /login/` — obtener tokens
- `POST /token/refresh/` — refrescar token
- `POST /verify-email/` — verificar email
- `GET /me/` — perfil actual

**Autenticación**: Simple JWT, token en header `Authorization: Bearer <token>`

### App `organization`

**Modelos**:
- `Organization` — entidad principal
- `Announcement` — anuncios de servicios
- `Service` — servicios ofrecidos
- `Pricing` — planes de precios
- `Catalog` — catálogo de servicios

**Superficies**:
- Rutas públicas (lectura sin auth, búsqueda WebSocket)
- Rutas protegidas (propietario de org)
- Rutas admin (`api/management/`)

**WebSocket**: `ws/organization/search/` — búsqueda en tiempo real (sin auth obligatoria, >3 caracteres)

### App `jobs`

**Modelos**:
- `Job` — contratación de un usuario a un anuncio
- Estados: `pending`, `active`, `completed`, `rejected`, `suspended`, `inactive`

**Ownership**: solo el dueño o staff pueden modificar

**Endpoints**:
- `GET /api/jobs/<uuid>/`
- `PATCH /api/jobs/<uuid>/`
- `DELETE /api/jobs/<uuid>/`
- `POST /api/announcements/<uuid>/jobs/` — crear job

### App `job_chat`

**Modelos**:
- `JobChat` — conversación (auto-creada al primer mensaje)
- `JobChatMessage` — mensaje
- `JobChatAttachment` — archivos adjuntos

**Superficies**:
- **REST**: `GET /api/jobs/<uuid>/messages/`, `POST /api/jobs/<uuid>/send/`
- **WebSocket**: `ws/jobs/<job_uuid>/chat/` — chat en tiempo real

**Seguridad**: solo dueño del job o staff pueden acceder

### App `assets`

**Sistema centralizado S3** con presigned URLs.

**Modelo `Asset`**:
- Ciclo de vida: `INITIATED` → `CONFIRMED` → `ATTACHED`
- Visibilidad: `public`, `protected`, `private`
- Campos: `pending_key` (temporal), `key` (final)

**Flujo de upload**:
1. `POST /api/assets/initiate-upload/` — crea Asset, genera PUT presigned URL
2. Cliente sube directo a S3
3. `POST /api/assets/<id>/complete/` — valida, mueve pending → confirmed

**Políticas** (`apps/assets/policies.py`): por `kind` — max_size, content_types, TTL, etc.

## Decisiones Técnicas

### 1. S3 Obligatorio

No hay fallback a filesystem. `USE_S3_STORAGE` debe estar siempre habilitado.

**Ventaja**: mismo código en dev (LocalStack) y producción (AWS S3).

### 2. JWT por Query String en WebSocket

El middleware WebSocket extrae token de `?token=...` además de headers HTTP.

**Razón**: navegadores no envían headers Authorization en WebSocket en algunos contextos.

**Logging**: errors estructurados en `apps/job_chat/views/consumers.py`.

### 3. Canales en Memoria en Desarrollo

Sin `REDIS_URL`, Channels usa `InMemoryChannelLayer` — funciona en desarrollo con un solo proceso.

En producción, `REDIS_URL` es obligatorio para multiproceso.

### 4. Docker Compose por Entorno

- `compose.yml` — desarrollo (todo en docker)
- `compose.prod.yml` — production-like (nginx, Redis, Daphne)
- `compose.prod-watchtower.yml` — producción con auto-updates

### 5. Fail-Fast en Producción

`Core/settings.py` endureciendo validaciones cuando `APP_MODE=production`:
- `DEBUG=0` forzado
- `SECURE_SSL_REDIRECT=True`
- `SECRET_KEY` obligatorio
- `ALLOWED_HOSTS` obligatorio
- `REDIS_URL` obligatorio

Verificar con: `python manage.py check --deploy`

## Seguridad

### Autenticación
- JWT (Simple JWT): tokens con TTL, refresh tokens rotados (condicional)
- Email verification requerida (bypaseable en dev)
- Password hashing con Django built-in

### Autorización
- `IsActiveAccount` — usuario verificado y activo
- `IsOwner` — solo propietario puede modificar
- `IsStaffOrReadOnly` — staff puede todo, otros leen
- Feature flags en DB para toggles sin deploy

### Rate Limiting
- Granular por endpoint (auth, organization, jobs)
- Configurable por variable de entorno
- Por IP o usuario

### CORS
- Desarrollo: `CORS_ALLOW_ALL_ORIGINS=True`
- Producción: explícitamente listados

### Headers de Seguridad
- `SECURE_HSTS_SECONDS=31536000` (1 año)
- `SECURE_HSTS_INCLUDE_SUBDOMAINS=True`
- `SECURE_SSL_REDIRECT=True` (producción)

## CI/CD

Pipeline en `.github/workflows/ci.yml`:
1. Build imagen Docker
2. Lint (Ruff)
3. Tests
4. `check --deploy` en modo producción

GitFlow simplificado:
- `master` — producción (requiere tag `vX.Y.Z`)
- `develop` — integración
- `feature/*` — trabajo funcional
- `hotfix/*` — fixes urgentes

Versionado SemVer en archivo `VERSION`.

## Monitoreo y Logs

- Logs a stdout/stderr (consumibles por Docker, ELK, etc.)
- Structured logging en componentes clave (WebSocket)
- Health endpoints: `GET /health/`
- Metrics disponibles (Prometheus-ready)

## Documentación Relacionada

- [ENVIRONMENT.md](./ENVIRONMENT.md) — Variables de entorno
- [OPERATIONS.md](./OPERATIONS.md) — Troubleshooting
- [WEBSOCKETS.md](./WEBSOCKETS.md) — Contratos WebSocket
- [STORAGE.md](./STORAGE.md) — Sistema de archivos S3
- [WORKFLOW.md](./WORKFLOW.md) — Ramas y versionado
