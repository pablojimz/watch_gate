# Aviso: Malware in twork-data-services-proxy-prime-api-v1-account-overdraft-info (GHSA-crw8-m6mj-q6qp)

## Resumen

Any computer that has this package installed or running should be considered fully compromised. All secrets and keys stored on that computer should be rotated immediately from a different computer. The package should be removed, but as full control of the computer may have been given to an outside entity, there is no guarantee that removing the package will remove all malicious software resulting from installing it.

## Paquetes afectados

- `twork-data-services-proxy-prime-api-v1-account-overdraft-info` (npm), versiones afectadas: = 20.7.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T16:38:17Z
- Fuente: https://github.com/advisories/GHSA-crw8-m6mj-q6qp

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `twork-data-services-proxy-prime-api-v1-account-overdraft-info`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
