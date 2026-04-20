# WebSockets

Documentación de endpoints WebSocket en tiempo real.

## Overview

El backend usa Django Channels para WebSocket. Dos superficies principales:

| Endpoint | Autenticación | Propósito |
|----------|---------------|-----------|
| `ws/organization/search/` | Opcional | Búsqueda de organizaciones en tiempo real |
| `ws/jobs/<job_uuid>/chat/` | Requerida | Chat de job (messages, typing) |

## 1. Organización Search (Público)

### Ruta

```
ws://localhost:8000/ws/organization/search/
wss://api.example.com/ws/organization/search/  (producción)
```

### Autenticación

**Opcional**. No requiere token.

Si se envía header `Authorization`, no se valida pero tampoco rechaza.

### Seguridad

- Rate limit por IP
- Query mínimo 3 caracteres
- Validación de origen (`AllowedHostsOriginValidator`)

### Mensaje de Entrada

Cliente → Servidor:

```json
{
  "q": "Acme"
}
```

Reglas:
- `q` es obligatorio y string
- Se aplica `strip()` para normalizar espacios
- Mínimo 3 caracteres después de normalizar
- Sin longitud máxima (se trunca en búsqueda)

### Mensaje de Salida (Éxito)

Servidor → Cliente:

```json
{
  "type": "search_results",
  "results": [
    {
      "id": "uuid",
      "name": "Acme Corp",
      "description": "...",
      "verified": true,
      "image_url": "https://..."
    }
  ],
  "query": "Acme"
}
```

Campos:
- `type`: siempre `search_results`
- `results`: array de organizaciones encontradas (máx 20)
- `query`: query original enviada

### Mensaje de Salida (Error)

Servidor → Cliente:

```json
{
  "type": "error",
  "message": "Query must be at least 3 characters",
  "code": "invalid_query"
}
```

Códigos de error:
- `invalid_query` — query < 3 caracteres o vacío
- `rate_limited` — demasiadas solicitudes desde esta IP
- `internal_error` — error del servidor

### Comportamiento

- Busca en `Organization.objects.filter(name__icontains=q)`
- Respeta visibilidad y validación de organizaciones
- Resultados limitados a 20 por query
- Conexión persiste mientras cliente permanezca conectado
- Se puede enviar múltiples queries en la misma conexión

### Ejemplo Cliente JavaScript

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/organization/search/');

ws.addEventListener('open', () => {
  ws.send(JSON.stringify({ q: 'Acme' }));
});

ws.addEventListener('message', (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'search_results') {
    console.log('Found orgs:', data.results);
  } else if (data.type === 'error') {
    console.error('Error:', data.message);
  }
});

ws.addEventListener('close', () => {
  console.log('Connection closed');
});
```

---

## 2. Job Chat (Autenticado)

### Ruta

```
ws://localhost:8000/ws/jobs/<job_uuid>/chat/?token=<jwt_token>
wss://api.example.com/ws/jobs/<job_uuid>/chat/?token=<jwt_token>  (producción)
```

**Nota**: Token se envía en query string (no en header) para compatibilidad con navegadores.

### Autenticación

**Requerida**. Dos opciones:

**Opción 1: Token en query string** (recomendado)

```
ws://localhost:8000/ws/jobs/abc-123/chat/?token=eyJ0eXAi...
```

**Opción 2: Token en header HTTP** (fallback)

```javascript
const headers = new Headers({
  'Authorization': 'Bearer eyJ0eXAi...'
});

// Algunos clientes no soportan headers personalizadas en WebSocket
```

Proceso de validación:
1. Extrae token de query string o header
2. Valida token JWT (signature, expiración)
3. Resuelve usuario
4. Verifica que usuario es owner del job o staff

Si falla: cierra conexión con código `4001` (Unauthorized).

### Autorización

Solo owner del job o staff pueden conectarse:

```python
# Si job.hired_user != request.user and no es staff:
# ❌ Rechaza conexión (4001)

# Si es owner o staff:
# ✅ Permite
```

### Seguridad

- Rate limit por usuario: `JOB_CHAT_WS_RATE_LIMIT` (default 100) mensajes por `JOB_CHAT_WS_RATE_WINDOW` (default 60 segundos)
- Una sola conexión WebSocket activa por (user, job) — desconecta la anterior si se abre otra
- Validación de origen

### Mensaje de Entrada

#### Enviar Mensaje

Cliente → Servidor:

```json
{
  "type": "message",
  "text": "Hola, ¿cómo estás?"
}
```

Reglas:
- `type` debe ser `message` o `typing`
- `text` es requerido si `type` es `message`
- Máximo `JOB_CHAT_ATTACHMENT_MAX_BYTES` (default 5MB) por adjunto
- Se replican a todos los conectados a ese job

#### Notificar Escritura

Cliente → Servidor:

```json
{
  "type": "typing"
}
```

No replica a otros; es informativo (puede usarse para UI "está escribiendo...").

### Mensaje de Salida

#### Nuevo Mensaje

Servidor → Clientes:

```json
{
  "type": "message",
  "id": "msg-uuid",
  "author": {
    "id": "user-uuid",
    "name": "John Doe",
    "avatar_url": "https://..."
  },
  "text": "Hola, ¿cómo estás?",
  "created_at": "2026-04-20T20:28:53Z",
  "attachments": [
    {
      "id": "att-uuid",
      "filename": "document.pdf",
      "content_type": "application/pdf",
      "download_url": "https://api.example.com/api/jobs/.../attachments/.../download"
    }
  ]
}
```

#### Confirmación de Escritura

Servidor → Clientes:

```json
{
  "type": "typing",
  "user_id": "user-uuid",
  "user_name": "Jane Smith"
}
```

#### Error

Servidor → Cliente:

```json
{
  "type": "error",
  "message": "Rate limited",
  "code": "rate_limited"
}
```

Códigos de error:
- `rate_limited` — excedió rate limit
- `invalid_message` — formato inválido
- `permission_denied` — no es owner/staff
- `internal_error` — error del servidor

### Comportamiento

- **Historial**: GET REST `/api/jobs/<uuid>/messages/` para recuperar historial
- **Adjuntos**: se suben vía REST `POST /api/jobs/<uuid>/send/` (multipart), no por WebSocket
- **Replicación**: cada usuario conectado recibe mensajes de otros en tiempo real
- **Ciclo de vida**: conexión persiste mientras cliente permanezca conectado

### Ejemplo Cliente JavaScript

```javascript
// Conectar
const token = 'eyJ0eXAi...';
const ws = new WebSocket(
  `ws://localhost:8000/ws/jobs/abc-123/chat/?token=${token}`
);

ws.addEventListener('open', () => {
  console.log('Connected');
});

ws.addEventListener('message', (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'message') {
    console.log(`${data.author.name}: ${data.text}`);
  } else if (data.type === 'typing') {
    console.log(`${data.user_name} está escribiendo...`);
  } else if (data.type === 'error') {
    console.error(`Error: ${data.message}`);
  }
});

// Enviar mensaje
function sendMessage(text) {
  ws.send(JSON.stringify({ type: 'message', text }));
}

// Notificar escritura
function notifyTyping() {
  ws.send(JSON.stringify({ type: 'typing' }));
}

ws.addEventListener('close', () => {
  console.log('Disconnected');
});
```

---

## Almacenamiento de Adjuntos

### Subir Adjunto

Endpoint REST: `POST /api/jobs/<uuid>/send/`

```bash
curl -X POST http://localhost:8000/api/jobs/abc-123/send/ \
  -H "Authorization: Bearer <token>" \
  -F "file=@document.pdf"
```

Respuesta:

```json
{
  "id": "msg-uuid",
  "type": "message",
  "text": null,
  "author": {...},
  "created_at": "2026-04-20T20:28:53Z",
  "attachments": [
    {
      "id": "att-uuid",
      "filename": "document.pdf",
      "content_type": "application/pdf",
      "size_bytes": 102400,
      "download_url": "https://api.example.com/api/jobs/.../attachments/.../download"
    }
  ]
}
```

### Descargar Adjunto

Endpoint REST: `GET /api/jobs/<uuid>/attachments/<att_uuid>/download/`

```bash
curl http://localhost:8000/api/jobs/abc-123/attachments/att-uuid/download/ \
  -H "Authorization: Bearer <token>"
```

Retorna:
- URL firmada con TTL (`JOB_CHAT_ATTACHMENT_URL_TTL_SECONDS`, default 1 hora)
- Headers para descargar directo desde S3

---

## Configuración Relevante

### Rate Limiting WebSocket

```env
JOB_CHAT_WS_RATE_LIMIT=100           # mensajes máximos
JOB_CHAT_WS_RATE_WINDOW=60           # en segundos
```

### Adjuntos

```env
JOB_CHAT_ATTACHMENT_MAX_BYTES=5242880                # 5MB
JOB_CHAT_ATTACHMENT_ALLOWED_CONTENT_TYPES=image/jpeg,image/png,application/pdf
JOB_CHAT_ATTACHMENT_URL_TTL_SECONDS=3600             # 1 hora
```

---

## Troubleshooting

### Conexión rechazada (401)

**Síntoma**: `4001 - Unauthorized`

**Causas**:
- Token inválido o expirado
- Usuario no es owner del job
- Usuario no es staff

**Solución**: Refrescar token, validar permisos.

### Rate Limited

**Síntoma**: Recibe `{"type": "error", "code": "rate_limited"}`

**Solución**: Esperar ventana de tiempo (`JOB_CHAT_WS_RATE_WINDOW`).

### Mensajes no llegan

**Síntoma**: Envía, pero otros usuarios no ven el mensaje

**Causas**:
- Redis no disponible (en multiproceso)
- Usuario desconectado antes de que se replique

**Solución**:
- Verificar Redis está running
- Revisar logs del server: `docker compose logs app`

### Adjuntos no se suben

**Síntoma**: `413 Payload Too Large` o `400 Bad Request`

**Causas**:
- Archivo > `JOB_CHAT_ATTACHMENT_MAX_BYTES`
- Content-Type no permitido

**Solución**: Revisar `ENVIRONMENT.md` para limits.

---

## Documentación Relacionada

- [ARCHITECTURE.md](./ARCHITECTURE.md) — Visión general, Channels
- [OPERATIONS.md](./OPERATIONS.md) — Troubleshooting Redis
- [ENVIRONMENT.md](./ENVIRONMENT.md) — Variables de configuración
