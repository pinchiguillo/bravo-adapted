# WebSocket de Busqueda de Organizaciones

## Objetivo

Documentar el contrato del endpoint WebSocket de busqueda de organizaciones, ya que no forma parte del esquema OpenAPI generado por `drf-spectacular`.

## Ruta

- `ws/organization/search/`

## Implementacion

- Routing: `backend/organization/routing.py`
- Consumer: `backend/organization/consumers.py`
- Registro ASGI: `backend/Core/asgi.py`

## Autenticacion

El handshake no requiere autenticacion.

Si el cliente envia una cabecera `Authorization`, el buscador no depende de ella para autorizar el acceso.

## Restricciones

- Requiere origen permitido por `AllowedHostsOriginValidator`.
- Aplica rate limit por visitante.
- La consulta debe incluir al menos 3 caracteres.

## Mensaje de entrada

Cliente -> servidor:

```json
{
  "q": "Acme"
}
```

Reglas:

- `q` es obligatorio.
- `q` se procesa con `strip()`.
- `q` debe tener al menos 3 caracteres tras normalizacion.

## Mensaje de salida correcto

Servidor -> cliente:

```json
{
  "type": "search.results",
  "query": "Acme",
  "results": [
    {
      "uuid": "00000000-0000-0000-0000-000000000000",
      "name": "Acme"
    }
  ]
}
```

Notas:

- `query` devuelve la cadena normalizada procesada por el servidor.
- `results` usa `OrganizationPublicSerializer`.
- Actualmente cada resultado expone `uuid`, `name`, `verification_level`, `is_approved` y `rating`.

## Mensajes de error

Consulta vacia:

```json
{
  "type": "search.error",
  "errors": {
    "q": "This field is required."
  }
}
```

Consulta demasiado corta:

```json
{
  "type": "search.error",
  "errors": {
    "q": "Ensure this field has at least 3 characters."
  }
}
```

Rate limit excedido:

```json
{
  "type": "search.error",
  "errors": {
    "detail": "Rate limit exceeded."
  }
}
```

## Semantica de busqueda

La busqueda filtra organizaciones por:

- `name__icontains`
- `legal_name__icontains`

Los resultados se ordenan por `name` y se limitan por `ORGANIZATION_SEARCH_WS_RESULT_LIMIT`.

## Relacion con drf-spectacular

`drf-spectacular` documenta los endpoints HTTP de la API, pero no este contrato WebSocket en el esquema OpenAPI actual.

## Cobertura de tests

La cobertura del socket esta en `backend/organization/tests.py` e incluye:

- resultado correcto
- validacion de query vacia
- validacion de longitud minima
- autenticacion requerida
- validacion de origen
- rate limit
