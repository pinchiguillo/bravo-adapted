# Índice de documentación

Este directorio se mantiene con una estructura lógica por dominios para facilitar navegación y mantenimiento.

## 1) Operación y entorno

- [Setup de desarrollo](setup-dev-env.md)
- [Variables de entorno](environment-variables.md)
- [Operación diaria](operacion.md)

## 2) Arquitectura y módulos

- [Arquitectura](arquitectura.md)

## 3) API y contratos

- [Swagger OpenAPI (YAML)](swagger.yaml)
- [Swagger estático (HTML)](swagger.html)
- [WS Auth Token Strategy](ws-auth-token-strategy.md)
- [WS Organization Search](ws-organization-search.md)

## 4) Flujo de repositorio y release

- [Workflow de ramas, CI/CD y versionado](workflow.md)

## 5) Reportes técnicos

- [Dev reports](devreports/README.md)

---

## Criterios de mantenimiento

- Un tema debe tener un único documento canónico (fuente de verdad).
- Si hay contenido histórico o de transición, debe indicarse explícitamente.
- Evitar duplicar comandos entre documentos; enlazar al documento canónico.
- Nuevos reportes de implementación deben ir a `devreports/` con prefijo de fecha `YYYY-MM-DD-...`.
