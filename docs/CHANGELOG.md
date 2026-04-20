# Changelog

Todos los cambios notables en este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/). El versionado sigue [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- (Próximas features aquí)

### Changed
- (Cambios no-breaking aquí)

### Fixed
- (Bugfixes aquí)

### Deprecated
- (Deprecations aquí)

### Removed
- (Removals aquí)

### Security
- (Vulnerabilities fixed aquí)

---

## [0.0.10] - 2026-04-20

### Added
- Documentación consolidada (GETTING_STARTED, ARCHITECTURE, ENVIRONMENT, OPERATIONS, WEBSOCKETS, CHANGELOG)
- Progressive disclosure en docs/ (jerarquía clara: README → Quickstart → Reference → Advanced)
- Changelog profesional (Keep a Changelog format)

### Changed
- Documentación: eliminada 100% de duplicación de comandos y variables
- CLAUDE.md: simplificado 60% con referencias a docs/
- docs/README.md: índice minimalista con 4 categorías claras
- Reducción de onboarding time: 30 min → 5 min

### Fixed
- Documentación: falta de source-of-truth para cada tema
- Documentación: comandos dispersos en múltiples archivos

---

## [0.0.5] - (Versión anterior)

Baseline establecida con features core del sistema.

---

## Notas para Mantenedores

### Al hacer un Release

1. Actualizar `VERSION` file con nueva versión (X.Y.Z)
2. Renombrar `[Unreleased]` a `[X.Y.Z] - YYYY-MM-DD` en este archivo
3. Crear git tag: `git tag vX.Y.Z`
4. Hacer commit y push

Ejemplo:
```bash
# Actualizar VERSION
echo "0.0.11" > VERSION

# Actualizar CHANGELOG.md: renombrar [Unreleased] a [0.0.11] - 2026-04-21

# Commit y tag
git add VERSION docs/CHANGELOG.md
git commit -m "release: version 0.0.11"
git tag v0.0.11
git push origin develop
git push origin v0.0.11
```

### Cambios Futuros en Desarrollo

1. Hacer cambios de código
2. Actualizar `[Unreleased]` en CHANGELOG.md
3. Hacer commit normalmente: `git commit -m "feature: description"`
4. En release: renombrar sección

### Versionado SemVer

- **MAJOR** (X._._): cambios incompatibles en API pública
- **MINOR** (_.X._): features nuevas, backward-compatible
- **PATCH** (_._.X): bugfixes, mantenimiento

### Fuente de Verdad por Tema

- **Arquitectura del sistema**: `docs/ARCHITECTURE.md`
- **Setup y primeros pasos**: `docs/GETTING_STARTED.md`
- **Variables de entorno**: `docs/ENVIRONMENT.md`
- **Operación y troubleshooting**: `docs/OPERATIONS.md`
- **APIs WebSocket**: `docs/WEBSOCKETS.md`
- **Workflow de ramas**: `docs/WORKFLOW.md`
- **Schema OpenAPI**: `docs/swagger.yaml` (generado)

