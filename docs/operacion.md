# Operación y Troubleshooting

## Comandos útiles

Desde `backend/`:

```bash
cp example.env .env
docker compose -f compose.yml up --build
docker compose -f compose.yml down
docker compose -f compose.yml ps
docker compose -f compose.yml logs -f app
docker compose -f compose.yml run --rm --no-deps app python manage.py showmigrations
docker compose -f compose.yml run --rm --no-deps app python manage.py test
docker compose -f compose.yml run --rm --no-deps -e APP_MODE=production -e DEBUG=0 -e ALLOWED_HOSTS=api.example.com -e CSRF_TRUSTED_ORIGINS=https://api.example.com -e SECRET_KEY=production-secret-key-with-enough-entropy-1234567890 app python manage.py check --deploy
docker compose -f compose.yml run --rm --no-deps app ruff check Core auth organization jobs manage.py
```

## Comprobaciones rápidas

### Estado de contenedores

```bash
docker compose -f compose.yml ps
```

Debe verse `app`, `postgres` y `localstack` en estado `running`.

### Imagen de producción para websockets

Construcción:

```bash
docker build -f backend/Dockerfile.prod -t bravo-backend:prod backend
```

Ejecución:

```bash
docker run --rm -p 8000:8000 \
  -e APP_MODE=production \
  -e DEBUG=0 \
  -e ALLOWED_HOSTS=tu-dominio.com,localhost \
  -e DATABASE_URL=postgresql://postgres:postgres@host.docker.internal:5432/auth_db \
  -e REDIS_URL=redis://host.docker.internal:6379/0 \
  bravo-backend:prod
```

En este modo el backend levanta `daphne` sobre `Core.asgi:application`, que es el runtime correcto para HTTP + WebSockets.

### Stack productivo básico con Compose

Desde `backend/`:

```bash
docker compose -f compose.prod.yml up --build -d
docker compose -f compose.prod.yml ps
docker compose -f compose.prod.yml logs -f app
```

Este archivo levanta:

- `app` en modo `production` con `daphne`
- `postgres` para la base de datos
- `redis` como channel layer para websockets
- `localstack` para S3/SES simulados

El orden de arranque queda definido así:

- `postgres`, `redis` y `localstack`
- `app` cuando sus dependencias están sanas
- `cloudflared` solo cuando `app` ya responde en `/health/`

### Cloudflare Tunnel opcional

La configuración del túnel se resuelve desde el dashboard de Cloudflare, así que no se monta ningún fichero local. Solo hace falta declarar el token en el `.env` que lee Docker Compose:

```env
CLOUDFLARED_TUNNEL_TOKEN=tu_token
```

Y arrancar el profile opcional:

```bash
docker compose -f compose.prod.yml --profile cloudflared up --build -d
```

`cloudflared` expone métricas internas y usa ese endpoint para su `healthcheck`.

### Salud de PostgreSQL

```bash
docker compose -f compose.yml logs postgres
```

El healthcheck usa `pg_isready -U postgres -d auth_db`.

### Salud de LocalStack

```bash
curl http://localhost:4566/_localstack/health
```

### Recursos AWS simulados (S3 y SES)

```bash
docker compose -f compose.yml exec -T localstack awslocal s3 ls
docker compose -f compose.yml exec -T localstack awslocal ses list-identities
```

## Errores comunes

### Error de conexión a DB

Causa:

- `DATABASE_URL` ausente o incorrecta en `app`.

Acción:

- Verificar `DATABASE_URL=postgresql://postgres:postgres@postgres:5432/auth_db`.

### Falla `check --deploy` en entorno local

Causa:

- Falta de variables obligatorias de producción (`APP_MODE=production`, `SECRET_KEY`, `ALLOWED_HOSTS`, etc).

Acción:

- Ejecutar `check --deploy` con variables de producción por línea de comando o en `.env` dedicado para producción.

### Fallo en instalación de dependencias

Causa:

- Falta `requirements.txt` o tiene paquetes inválidos.

Acción:

- Crear/ajustar `requirements.txt` y reconstruir.

### Fallo del lint en CI

Causa:

- Importes no ordenados o errores detectados por `ruff`.

Acción:

- Ejecutar `docker compose -f compose.yml run --rm --no-deps app ruff check Core auth organization jobs manage.py`.
- Si aplica, corregir automaticamente con `docker compose -f compose.yml run --rm --no-deps app ruff check Core auth organization jobs manage.py --fix`.

### Errores al enviar email con SES

Causa:

- `USE_SES_EMAIL=1` sin identidad verificada en LocalStack.
- `DEFAULT_FROM_EMAIL` no coincide con una identidad en SES.

Acción:

- Verificar identidades: `awslocal ses list-identities`.
- Crear identidad manual: `awslocal ses verify-email-identity --email-address <email>`.

## Regla operativa

Para evitar inconsistencias de entorno:
- Ejecutar cualquier comando Python/Django siempre dentro del servicio `app`.
- No ejecutar `python`, `manage.py` ni `pytest` directamente sobre el host.

## CI

El pipeline automático está en `.github/workflows/backend-ci.yml` y ejecuta:

- build de imagen `app`
- lint (`ruff check Core auth organization jobs manage.py`)
- tests (`manage.py test`)
- `check --deploy` en modo producción

## Gobernanza de repositorio

Para la estructura recomendada del repo, estrategia de ramas y validaciones pre-merge:

- `docs/repositorio-ramas-validaciones.md`
