# Aviso: Malware in @yane88/term-reqable-01 (GHSA-m76v-4h4c-w693)

## Resumen

Any computer that has this package installed or running should be considered fully compromised. All secrets and keys stored on that computer should be rotated immediately from a different computer. The package should be removed, but as full control of the computer may have been given to an outside entity, there is no guarantee that removing the package will remove all malicious software resulting from installing it.

## Paquetes afectados

- `@yane88/term-reqable-01` (npm), versiones afectadas: >= 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-01T02:29:07Z
- Fuente: https://github.com/advisories/GHSA-m76v-4h4c-w693

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `@yane88/term-reqable-01`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
