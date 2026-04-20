# Workflow de ramas, versionado, publicación de imágenes y despliegue

## Objetivo

Definir un flujo de trabajo simple y operativo para:

- separar claramente desarrollo y producción;
- permitir fixes urgentes sobre producción sin mezclar trabajo en curso;
- generar imágenes Docker distintas para dev y prod;
- desplegar automáticamente en cada entorno;
- mantener trazabilidad completa entre commit, versión e imagen desplegada.

---

## Estrategia recomendada

La estrategia recomendada es un **GitFlow simplificado**:

- `master`: rama estable de producción.
- `develop`: rama de integración para desarrollo.
- `feature/*`: ramas cortas para trabajo funcional.
- `hotfix/*`: ramas cortas para corregir incidencias urgentes en producción.

No se recomienda empezar con `release/*` salvo que exista una fase formal de congelación, QA o validación previa a producción.

---

## Estructura de ramas

### `master`

Rama de producción.

Reglas:

- Siempre debe estar en estado desplegable.
- No se permite push directo.
- Todo cambio entra mediante Pull Request.
- Cada release de producción debe etiquetarse con un tag Git del tipo `vX.Y.Z`.

Uso:

- recibe merges de `hotfix/*`;
- opcionalmente puede recibir merges controlados desde `develop` cuando se quiera promover una versión a producción.

### `develop`

Rama de integración de desarrollo.

Reglas:

- Aquí se integran features y fixes que todavía no son release de producción.
- Cada merge puede disparar build, publicación de imagen y despliegue automático al entorno dev.
- No se permite push directo si se quiere mantener control de calidad.

Uso:

- recibe merges desde `feature/*`;
- recibe back-merge de `hotfix/*` para no perder fixes hechos en producción.

### `feature/*`

Ramas de trabajo funcional.

Convención sugerida:

- `feature/login-google`
- `feature/refactor-orders-service`
- `feature/add-payment-retry`

Reglas:

- nacen desde `develop`;
- se fusionan a `develop` mediante Pull Request;
- deben ser ramas cortas y acotadas.

### `hotfix/*`

Ramas para incidentes urgentes en producción.

Convención sugerida:

- `hotfix/1.8.5-fix-timeout`
- `hotfix/1.8.6-fix-null-pointer`

Reglas:

- nacen desde `master`;
- se fusionan primero a `master` para corregir producción;
- después deben fusionarse también a `develop` para mantener ambos carriles alineados.

---

## Flujo operativo

### 1. Desarrollo normal

1. Se crea una rama `feature/*` desde `develop`.
2. Se implementa el cambio.
3. Se abre Pull Request contra `develop`.
4. Al hacer merge en `develop`:
   - se construye la imagen Docker;
   - se publica en el registry con tags de dev;
   - se despliega automáticamente al entorno development.

### 2. Fix urgente en producción

1. Se crea una rama `hotfix/*` desde `master`.
2. Se implementa la corrección.
3. Se abre Pull Request contra `master`.
4. Al hacer merge en `master`:
   - se crea un tag Git de release, por ejemplo `v1.8.5`;
   - se construye la imagen Docker de producción;
   - se publica en el registry con tags de prod;
   - se despliega automáticamente a production.
5. Ese mismo fix se fusiona después a `develop`.

---

## Tags automáticos

El versionado por tags se ejecuta de forma **100% automática** en ambas ramas principales:

- `master`: crea tags estables `vX.Y.Z` en cada push.
- `develop`: crea tags de pre-release `vX.Y.Z-dev.N.<sha>` en cada push.

Los tags de `master` son la referencia para publicación de imágenes de producción.
Los tags de `develop` permiten trazabilidad continua del estado de integración.

---

## Política de versionado

Se recomienda **SemVer** para producción:

- `MAJOR`: cambios incompatibles;
- `MINOR`: nuevas funcionalidades compatibles;
- `PATCH`: correcciones.

Ejemplos:

- `1.8.4`
- `1.8.5`
- `2.0.0`

La versión puede mantenerse en un archivo `VERSION` en la raíz del repositorio.

Ejemplo:

```text
1.8.4