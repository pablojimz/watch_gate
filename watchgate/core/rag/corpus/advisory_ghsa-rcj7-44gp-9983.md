# Aviso: Malicious code in grafeno-actions (npm) (GHSA-rcj7-44gp-9983)

## Resumen

The OpenSSF Package Analysis project identified 'grafeno-actions' @ 999.0.0 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `grafeno-actions` (npm), versiones afectadas: = 999.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T00:30:26Z
- Fuente: https://github.com/advisories/GHSA-rcj7-44gp-9983

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `grafeno-actions`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
