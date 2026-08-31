# Aviso: Malware in zenntechinc-cli (GHSA-6wh9-pcqw-jp9j)

## Resumen

Any computer that has this package installed or running should be considered fully compromised. All secrets and keys stored on that computer should be rotated immediately from a different computer. The package should be removed, but as full control of the computer may have been given to an outside entity, there is no guarantee that removing the package will remove all malicious software resulting from installing it.

## Paquetes afectados

- `zenntechinc-cli` (npm), versiones afectadas: = 1.6.6
- `zenntechinc-cli` (npm), versiones afectadas: = 1.6.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T16:45:08Z
- Fuente: https://github.com/advisories/GHSA-6wh9-pcqw-jp9j

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `zenntechinc-cli`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
