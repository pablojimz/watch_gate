# Aviso: Malicious code in omniauth-recharge-rails-example (npm) (GHSA-88ff-297x-5h43)

## Resumen

The OpenSSF Package Analysis project identified 'omniauth-recharge-rails-example' @ 1.0.0 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `omniauth-recharge-rails-example` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T09:31:32Z
- Fuente: https://github.com/advisories/GHSA-88ff-297x-5h43

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `omniauth-recharge-rails-example`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
