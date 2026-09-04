# Aviso: Malware in matrix-by-lmx (GHSA-jhgv-vh9h-q3r9)

## Resumen

Any computer that has this package installed or running should be considered fully compromised. All secrets and keys stored on that computer should be rotated immediately from a different computer. The package should be removed, but as full control of the computer may have been given to an outside entity, there is no guarantee that removing the package will remove all malicious software resulting from installing it.

## Paquetes afectados

- `matrix-by-lmx` (npm), versiones afectadas: >= 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-01T01:51:59Z
- Fuente: https://github.com/advisories/GHSA-jhgv-vh9h-q3r9

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `matrix-by-lmx`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
