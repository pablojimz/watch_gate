# Aviso: Malware in svelte-cls-ui (GHSA-f6cw-gvwj-gw7f)

## Resumen

Any computer that has this package installed or running should be considered fully compromised. All secrets and keys stored on that computer should be rotated immediately from a different computer. The package should be removed, but as full control of the computer may have been given to an outside entity, there is no guarantee that removing the package will remove all malicious software resulting from installing it.

## Paquetes afectados

- `svelte-cls-ui` (npm), versiones afectadas: >= 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T16:47:36Z
- Fuente: https://github.com/advisories/GHSA-f6cw-gvwj-gw7f

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `svelte-cls-ui`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
