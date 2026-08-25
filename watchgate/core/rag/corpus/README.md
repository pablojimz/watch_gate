# Corpus del RAG de WatchGate

Este directorio es la fuente de conocimiento del sistema RAG: cada `.md` es
un caso de ataque, técnica MITRE ATT&CK o aviso de seguridad que la capa
semántica recupera para dárselo como contexto al LLM en cada análisis.

> **Documentación completa**: [`docs/manual_rag.md`](../../../../docs/manual_rag.md).

## Tipos de fichero

| Patrón | Prefijo del H1 | Origen |
|--------|----------------|--------|
| `attck_*.md` | `# MITRE ATT&CK ...` | Fichas de técnica MITRE, curadas a mano |
| `advisory_*.md` | `# Aviso: ...` | Sincronizados de GitHub Advisories (`watchgate rag sync-cves`) — **no editar a mano** |
| (resto) | `# Caso: ...` / `# Técnica: ...` / `# Patrón: ...` | Casos reales y patrones, curados a mano |

## Añadir un caso a mano

1. Crea un `.md` siguiendo la plantilla (sección 3 del manual): H1 con
   prefijo de tipo, `## Resumen`, `## Vector de introducción`,
   `## Patrón a vigilar` + línea de técnica MITRE.
2. Reindexa: `watchgate rag reindex`.

El **patrón a vigilar** debe ser concreto y accionable (lo que se vería en
un diff), no un consejo genérico. El RAG existe para dar al modelo
conocimiento que no tiene por defecto: detalle verificable de incidentes
reales, no abstracciones.

## Ficheros `advisory_*`

Los genera y actualiza `watchgate rag sync-cves` de forma idempotente. No se
editan a mano (la siguiente sincronización los sobrescribiría). Para dejar
de trackearlos y que cada instancia se los baje sola, se pueden añadir a
`.gitignore`; versionarlos hace el corpus reproducible sin red.
