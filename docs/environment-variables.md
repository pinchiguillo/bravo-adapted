# Variables de entorno

Este documento resume las variables consumidas por el backend desde `Core/settings.py` y `example.env`.

## Configuracion general

- `APP_MODE`: modo de ejecucion. Valores habituales: `development`, `production`.
- `PORT`: puerto expuesto por el contenedor `app`.
- `SECRET_KEY`: clave secreta de Django.
- `DEBUG`: activa o desactiva modo debug.
- `ALLOWED_HOSTS`: lista separada por comas de hosts permitidos.
- `CSRF_TRUSTED_ORIGINS`: lista separada por comas de origenes confiables para CSRF.
- CORS: cuando `APP_MODE=development`, el backend permite todos los origenes (`CORS_ALLOW_ALL_ORIGINS=True`). En `production` queda desactivado.

## Seguridad HTTP y cookies

- `SECURE_SSL_REDIRECT`
- `SECURE_HSTS_SECONDS`
- `SECURE_HSTS_INCLUDE_SUBDOMAINS`
- `SECURE_HSTS_PRELOAD`
- `SESSION_COOKIE_SECURE`
- `CSRF_COOKIE_SECURE`
- `SECURE_PROXY_SSL_HEADER`: formato `HEADER_NAME,header_value`

En `APP_MODE=production` varias de estas opciones se endurecen automaticamente.

## Base de datos y canales

- `DATABASE_URL`: cadena PostgreSQL usada por Django.
- `REDIS_URL`: backend de canales para WebSocket y mensajeria.

Si `REDIS_URL` no existe fuera de produccion, Channels usa `InMemoryChannelLayer`.

## AWS, almacenamiento y correo

- `AWS_DEFAULT_REGION`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `LOCALSTACK_ENDPOINT`
- `AWS_S3_ENDPOINT_URL`
- `AWS_SES_ENDPOINT_URL`
- `AWS_STORAGE_BUCKET_NAME`
- `USE_S3_STORAGE` (debe permanecer en `1`; el proyecto exige storage S3 activo)
- `USE_SES_EMAIL`
- `DEFAULT_FROM_EMAIL`

## SMTP adicional

- `EMAIL_BACKEND`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- `EMAIL_USE_SSL`

## PostgreSQL del contenedor local

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

## Auth y JWT

- `AUTH_VERIFY_EMAIL_URL_TEMPLATE`: URL base para verificacion de email.
- `AUTH_BYPASS_EMAIL_VERIFICATION`: cuando vale `1`, omite la verificacion de email en toda la app (auth, endpoints protegidos y acceso jobs/ws). En desarrollo el valor por defecto es `1`; en produccion el valor por defecto es `0`.
- `BYPASS_ADMIN_LOGIN`: cuando vale `1`, desactiva el requisito de autenticacion y permisos admin en los endpoints de `api/management/`. Su valor por defecto es `0` y en produccion se fuerza automaticamente a `0`. Tambien puede referenciarse como `Bypass_Admin_Login` a nivel funcional, pero la variable real de entorno es `BYPASS_ADMIN_LOGIN`.
- `BYPASS_ORGANIZATION_VALIDATION`: cuando vale `1`, trata las organizaciones como validadas para reglas de visibilidad y escritura. En produccion se fuerza automaticamente a `0`.
- `AUTH_ENFORCE_PASSWORD_RESTRICTIONS`: cuando vale `0`, desactiva validadores de Django y longitud minima en serializers para permitir contrasenas sin restricciones.
- `HIDE_API_DOCS`: cuando vale `1`, elimina del enrutado las rutas `api/docs/` y `api/schema/`, dejandolas no disponibles. Por defecto vale `0` en desarrollo y `1` en produccion.
- `JWT_ROTATE_REFRESH_TOKENS`: rota refresh tokens al renovar sesion.

## Jobs y WebSocket

- `JOB_CHAT_ATTACHMENT_MAX_BYTES`: limite de tamano de adjuntos.
- `JOB_CHAT_ATTACHMENT_ALLOWED_CONTENT_TYPES`: lista separada por comas de content types permitidos.
- `JOB_CHAT_WS_RATE_LIMIT`: maximo de mensajes por ventana.
- `JOB_CHAT_WS_RATE_WINDOW`: tamano de ventana para rate limit en segundos.

## Throttling DRF

Variables disponibles:

- `AUTH_DEFAULT_THROTTLE_RATE`
- `AUTH_LOGIN_THROTTLE_RATE`
- `AUTH_REGISTER_THROTTLE_RATE`
- `AUTH_REFRESH_THROTTLE_RATE`
- `AUTH_VERIFY_EMAIL_THROTTLE_RATE`
- `ORGANIZATION_DEFAULT_THROTTLE_RATE`
- `ORGANIZATION_PUBLIC_READ_THROTTLE_RATE`
- `ORGANIZATION_AUTHENTICATED_READ_THROTTLE_RATE`
- `ORGANIZATION_WRITE_THROTTLE_RATE`
- `ORGANIZATION_ADMIN_THROTTLE_RATE`
- `JOBS_DEFAULT_THROTTLE_RATE`
- `JOBS_READ_THROTTLE_RATE`
- `JOBS_WRITE_THROTTLE_RATE`
- `JOBS_MESSAGES_THROTTLE_RATE`
- `JOBS_ATTACHMENTS_THROTTLE_RATE`

## Otras variables presentes en `example.env`

- `CLOUDFLARED_TUNNEL_TOKEN`: soporte de tunel/local exposure cuando aplique.

## Referencia practica

- Plantilla base: `example.env`
- Swagger UI local: `http://localhost:8000/api/docs/` si `HIDE_API_DOCS=0`
- OpenAPI schema: `http://localhost:8000/api/schema/` si `HIDE_API_DOCS=0`
