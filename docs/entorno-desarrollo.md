# Entorno de Desarrollo

## Objetivo

Proveer un entorno reproducible para backend con:

- aplicación Django,
- PostgreSQL local,
- servicios AWS simulados vía LocalStack.

## Archivos clave

- `backend/compose.yml`: orquestación de servicios.
- `backend/Dockerfile`: imagen base de `app`.
- `backend/entrypoint.sh`: secuencia de arranque de `app`.

## Arranque

1. Entrar en `backend/`.
2. Crear `.env` local desde el ejemplo.
3. Levantar servicios.

```bash
cp example.env .env
docker compose -f compose.yml up --build
```

## Regla de ejecucion de comandos Django

No ejecutar `python`, `manage.py` o `pytest` directamente en host.
Usar siempre Docker Compose desde `backend/`:

```bash
docker compose -f compose.yml run --rm --no-deps app python manage.py <comando>
```

## Servicios y puertos

- `app`: `localhost:8000`
- `postgres`: solo red interna de Docker (`postgres:5432`)
- `localstack`: `localhost:4566`

## Variables de entorno relevantes (`app`)

Se gestionan desde `backend/.env` (referencia: `backend/example.env`).
Variables clave:

- `APP_MODE`
- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL`
- `REDIS_URL`
- `SECURE_*` y cookies (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`)
- AWS/SES/S3 (`AWS_*`, `USE_S3_STORAGE`, `USE_SES_EMAIL`, `DEFAULT_FROM_EMAIL`)

## Volúmenes

- Código fuente: `.:/app`
- Datos PostgreSQL: `postgres_data`
- Datos LocalStack: `localstack_data`

## Flujo de inicialización de `app`

`entrypoint.sh`:

1. `python manage.py migrate`,
2. `python manage.py runserver 0.0.0.0:8000` en desarrollo,
3. `daphne -b 0.0.0.0 -p 8000 Core.asgi:application` en producción si `APP_MODE=production`.

## Validaciones recomendadas

- Verificar que `app` arranca sin errores de importación.
- Verificar que migraciones se aplican (`manage.py migrate`).
- Verificar conectividad a PostgreSQL (`postgres:5432` desde contenedor `app`).
- Verificar endpoint de LocalStack (`http://localhost:4566/_localstack/health`).
- Verificar lint:

```bash
docker compose -f compose.yml run --rm --no-deps app \
  ruff check Core auth organization jobs manage.py
```

- Verificar checks de despliegue con variables de producción:

```bash
docker compose -f compose.yml run --rm --no-deps \
  -e APP_MODE=production \
  -e DEBUG=0 \
  -e ALLOWED_HOSTS=api.example.com \
  -e CSRF_TRUSTED_ORIGINS=https://api.example.com \
  -e SECRET_KEY=production-secret-key-with-enough-entropy-1234567890 \
  app python manage.py check --deploy
```

- Verificar bucket S3 creado por bootstrap:

```bash
docker compose -f compose.yml exec -T localstack awslocal s3 ls
```

- Verificar identidad SES simulada:

```bash
docker compose -f compose.yml exec -T localstack awslocal ses list-identities
```

## Nota sobre SES en LocalStack

LocalStack emula la API de SES para desarrollo, pero no entrega correos reales a Internet.
Permite validar integración, payload y flujos de negocio sin enviar emails externos.

## Notas operativas

- `compose.yml` cubre desarrollo con `app`, `postgres` y `localstack`.
- `compose.prod.yml` añade `redis` y permite `cloudflared` como profile opcional.
- La estrategia JWT en WebSocket sigue siendo por querystring por compatibilidad. Ver `backend/docs/ws-auth-token-strategy.md`.
