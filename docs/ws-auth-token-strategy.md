# Decision - estrategia de token en WebSocket (JWT)

Fecha: 2026-03-10
Contexto: autenticacion de sockets en `backend/jobs/ws_auth.py`.

## Decision
Se mantiene temporalmente la autenticacion por `token` en querystring para compatibilidad con clientes actuales.

## Justificacion
- El contrato actual ya usa `?token=<jwt>` en el handshake WebSocket.
- Cambiar de inmediato a otro mecanismo (por ejemplo cookie HttpOnly o subprotocol) rompe clientes existentes.
- El riesgo principal no es de validacion JWT (ya se valida), sino de exposicion accidental del token en logs.

## Medidas aplicadas
- Middleware endurecido con excepciones especificas (`InvalidToken`, `TokenError`, `AuthenticationFailed`, `ValueError`).
- Logging estructurado sin incluir el token ni el querystring completo.
- Eventos de fallo incluyen solo metadatos operativos: `reason`, `path`, `token_source`.

## Plan de evolucion recomendado
1. Mantener querystring durante una ventana de compatibilidad.
2. Introducir autenticacion por cookie segura/HttpOnly o encabezado negociado por subprotocol.
3. Desactivar querystring cuando todos los clientes migren.
