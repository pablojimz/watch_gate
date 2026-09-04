# Aviso: Malicious code in ally-call-wait-time (npm) (GHSA-7wgr-w2fw-hph3)

## Resumen

The package ally-call-wait-time was found to contain malicious code.

The OpenSSF Package Analysis project identified 'ally-call-wait-time' @ 99.99.99 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `ally-call-wait-time` (npm), versiones afectadas: = 99.99.99
- `ally-call-wait-time` (npm), versiones afectadas: = 100.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T23:15:24Z
- Fuente: https://github.com/advisories/GHSA-7wgr-w2fw-hph3

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `ally-call-wait-time`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
