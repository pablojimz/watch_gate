# Aviso: Malicious code in autobahn-electron-probe (npm) (GHSA-8jx3-79xq-v4q4)

## Resumen

The OpenSSF Package Analysis project identified 'autobahn-electron-probe' @ 99.99.1 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `autobahn-electron-probe` (npm), versiones afectadas: = 99.99.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T00:30:26Z
- Fuente: https://github.com/advisories/GHSA-8jx3-79xq-v4q4

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `autobahn-electron-probe`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
