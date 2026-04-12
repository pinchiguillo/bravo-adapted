# Storage S3 para archivos

Este documento describe el funcionamiento canonico del almacenamiento de archivos del backend sobre S3 compatible. En desarrollo se usa LocalStack; en despliegue la misma configuracion apunta a un endpoint S3 real o compatible.

## Resumen

- El storage de Django para archivos de negocio siempre es `storages.backends.s3.S3Storage`.
- El proyecto no admite desactivar S3: `USE_S3_STORAGE` debe permanecer habilitado.
- En local, el backend se conecta internamente a `localstack:4566`.
- Las URLs publicas de media se construyen por defecto bajo `/s3/<bucket>/...` para que `nginx` las proxyee hacia LocalStack.

## Configuracion

La configuracion vive en [Core/settings.py](../Core/settings.py).

Variables principales:

- `AWS_DEFAULT_REGION`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_ENDPOINT_URL`
- `AWS_STORAGE_BUCKET_NAME`
- `MEDIA_PUBLIC_BASE_URL`
- `USE_S3_STORAGE`

Comportamiento relevante:

- `AWS_S3_ENDPOINT_URL` cae por defecto a `http://localstack:4566`.
- `MEDIA_PUBLIC_BASE_URL` cae por defecto a `/s3`.
- Si `USE_S3_STORAGE=0`, el backend falla al arrancar con `ImproperlyConfigured`.
- En produccion se exigen credenciales y bucket por entorno.

## Backend Django

Cuando S3 esta activo:

- `storages` se agrega a `INSTALLED_APPS`.
- `STORAGES["default"]` usa `storages.backends.s3.S3Storage`.
- Se fuerza `AWS_S3_SIGNATURE_VERSION=s3v4`.
- Se usa `AWS_S3_ADDRESSING_STYLE=path`.
- `AWS_S3_FILE_OVERWRITE=False` para no sobrescribir nombres existentes.
- `AWS_QUERYSTRING_AUTH=True` para permitir URLs firmadas cuando el backend de storage las soporte.

La `MEDIA_URL` se construye asi:

1. Si existe `MEDIA_PUBLIC_BASE_URL`, usa `<base>/<bucket>/`.
2. Si no, y existe `AWS_S3_ENDPOINT_URL`, usa `<endpoint>/<bucket>/`.
3. Como ultimo fallback, usa `https://<bucket>.s3.amazonaws.com/`.

## Proxy y acceso publico

La publicacion local de archivos se resuelve en [dev.conf](../docker/nginx/dev.conf):

- `nginx` recibe peticiones `GET /s3/...`
- reescribe el prefijo `/s3/`
- reenvia la solicitud a `http://localstack:4566`

Eso permite que las URLs generadas por Django sean accesibles desde fuera del contenedor sin exponer directamente `localstack:4566`.

## Recursos que usan storage S3

Actualmente los `FileField`/`ImageField` persistidos en S3 son:

- [models.py](../apps/auth/models.py): `CustomUser.avatar` en `avatars/`
- [models.py](../apps/job_chat/models.py): `JobChatAttachment.file` en `job-chat-attachments/%Y/%m/%d/`
- [announcement.py](../apps/organization/models/announcement.py): `AnnouncementImage.image` en `organization-announcements/%Y/%m/%d/`

## Flujo de subida

1. El cliente envia un `multipart/form-data` al endpoint DRF correspondiente.
2. El serializer valida tipo y tamano del archivo.
3. Al ejecutar `serializer.save()`, Django escribe el fichero en el storage S3 configurado.
4. En base de datos solo se persiste la clave del objeto, no el binario.

Validaciones actuales:

- Adjuntos de chat: [serializers.py](../apps/job_chat/serializers.py)
  - tipos permitidos por `JOB_CHAT_ATTACHMENT_ALLOWED_CONTENT_TYPES`
  - tamano maximo por `JOB_CHAT_ATTACHMENT_MAX_BYTES`
- Imagenes de anuncios: [announcement.py](../apps/organization/serializers/announcement.py)
  - tipos permitidos por `ORGANIZATION_ANNOUNCEMENT_IMAGE_ALLOWED_CONTENT_TYPES`
  - tamano maximo por `ORGANIZATION_ANNOUNCEMENT_IMAGE_MAX_BYTES`

## Flujo de descarga y exposicion

Hay dos patrones de acceso:

### 1. URL publica/proxied de media

Para campos que exponen directamente `obj.image.url` u otra URL del storage, Django devuelve una ruta basada en `MEDIA_URL`, normalmente `/s3/<bucket>/<key>`. Si la URL es relativa, el serializer la vuelve absoluta con `request.build_absolute_uri(...)`.

Este patron se usa, por ejemplo, en las imagenes de anuncios:

- [announcement.py](../apps/organization/serializers/announcement.py)

### 2. Endpoint backend que entrega URL temporal

Los adjuntos del chat no exponen la URL cruda del objeto. En su lugar:

- el serializer devuelve un endpoint de negocio `download_url`
- el backend valida permisos
- luego responde con la URL final del storage y su TTL

Implementacion:

- [serializers.py](../apps/job_chat/serializers.py)
- [views.py](../apps/job_chat/views.py)

Reglas:

- se intenta `storage.url(name, expire=ttl)` usando `JOB_CHAT_ATTACHMENT_URL_TTL_SECONDS`
- si el backend no acepta `expire`, se hace fallback a `storage.url(name)`
- si la URL retornada es relativa, se transforma en absoluta

## LocalStack en desarrollo

El bootstrap local crea automaticamente los recursos minimos:

- bucket S3 `AWS_STORAGE_BUCKET_NAME`
- identidad SES `DEFAULT_FROM_EMAIL`

Script:

- [10-aws-bootstrap.sh](../docker/localstack/init/10-aws-bootstrap.sh)

Comprobacion de integracion:

- [tests.py](../common/tests.py)

Ese test confirma que:

- el bucket existe
- subir un avatar realmente persiste el objeto en S3/LocalStack

## Referencias relacionadas

- [environment-variables.md](../docs/environment-variables.md)
- [operacion.md](../docs/operacion.md)
- [arquitectura.md](../docs/arquitectura.md)
