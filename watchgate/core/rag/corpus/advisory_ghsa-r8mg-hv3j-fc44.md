# Aviso: Malware in tool-registry-scripts (GHSA-r8mg-hv3j-fc44)

## Resumen

Any computer that has this package installed or running should be considered fully compromised. All secrets and keys stored on that computer should be rotated immediately from a different computer. The package should be removed, but as full control of the computer may have been given to an outside entity, there is no guarantee that removing the package will remove all malicious software resulting from installing it.

## Paquetes afectados

- `tool-registry-scripts` (npm), versiones afectadas: >= 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-07T16:17:40Z
- Fuente: https://github.com/advisories/GHSA-r8mg-hv3j-fc44

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `tool-registry-scripts`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
