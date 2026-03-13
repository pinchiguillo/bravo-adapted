# Decision - estrategia de token en WebSocket (JWT)

Fecha: 2026-03-10
Actualizado: 2026-03-12
Contexto: autenticacion de sockets en `backend/jobs/ws_auth.py`.

## Decision
La autenticacion WebSocket vigente usa el encabezado `Authorization: Bearer <jwt>` durante el handshake.

## Justificacion
- El middleware actual extrae el JWT desde la cabecera `Authorization`.
- Evita exponer tokens en querystring y reduce el riesgo de fuga en logs o trazas.
- El contrato actual de tests en `jobs` y `organization` ya valida este mecanismo.

## Medidas aplicadas
- Middleware endurecido con excepciones especificas (`InvalidToken`, `TokenError`, `AuthenticationFailed`, `ValueError`).
- Logging estructurado sin incluir el token.
- Eventos de fallo incluyen solo metadatos operativos: `reason`, `path`, `token_source`.

## Plan de evolucion recomendado
1. Mantener `Authorization: Bearer` como contrato por defecto.
2. Evaluar autenticacion por cookie segura/HttpOnly si aparecen clientes browser-first con esa necesidad.
3. Mantener la documentacion de cada socket por separado del esquema OpenAPI HTTP.
