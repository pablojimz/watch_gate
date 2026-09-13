# Aviso: Malicious code in @cp-shared-14/frontend-ui (npm) (GHSA-3f8m-gfc3-3g2m)

## Resumen

The OpenSSF Package Analysis project identified '@cp-shared-14/frontend-ui' @ 6.3.4 (npm) as malicious.

It is considered malicious because:

- The package communicates with a domain associated with malicious activity.

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `@cp-shared-14/frontend-ui` (npm), versiones afectadas: = 6.3.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-07T21:30:23Z
- Fuente: https://github.com/advisories/GHSA-3f8m-gfc3-3g2m

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `@cp-shared-14/frontend-ui`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
