# Aviso: Malicious code in fuels-core (npm) (GHSA-w76m-93w4-w9vj)

## Resumen

The OpenSSF Package Analysis project identified 'fuels-core' @ 1.0.0 (npm) as malicious.

It is considered malicious because:

- The package communicates with a domain associated with malicious activity.

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `fuels-core` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T00:30:26Z
- Fuente: https://github.com/advisories/GHSA-w76m-93w4-w9vj

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `fuels-core`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
