# Aviso: Malware in tset_racie (GHSA-7978-5fh2-74q2)

## Resumen

Any computer that has this package installed or running should be considered fully compromised. All secrets and keys stored on that computer should be rotated immediately from a different computer. The package should be removed, but as full control of the computer may have been given to an outside entity, there is no guarantee that removing the package will remove all malicious software resulting from installing it.

## Paquetes afectados

- `tset_racie` (npm), versiones afectadas: >= 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T22:09:18Z
- Fuente: https://github.com/advisories/GHSA-7978-5fh2-74q2

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `tset_racie`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
