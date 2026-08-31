# Aviso: Malicious code in fuels-typegen (npm) (GHSA-4f4x-3qvc-wffh)

## Resumen

The OpenSSF Package Analysis project identified 'fuels-typegen' @ 1.0.0 (npm) as malicious.

It is considered malicious because:

- The package communicates with a domain associated with malicious activity.

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `fuels-typegen` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T00:30:26Z
- Fuente: https://github.com/advisories/GHSA-4f4x-3qvc-wffh

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `fuels-typegen`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
