# Aviso: Malicious code in com.db.autobahn.notification-center-electron (npm) (GHSA-q6wc-5f8x-wwwj)

## Resumen

The OpenSSF Package Analysis project identified 'com.db.autobahn.notification-center-electron' @ 88.88.2 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `com.db.autobahn.notification-center-electron` (npm), versiones afectadas: = 88.88.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T00:30:26Z
- Fuente: https://github.com/advisories/GHSA-q6wc-5f8x-wwwj

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `com.db.autobahn.notification-center-electron`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
