# Aviso: Malicious code in ally-allowlist (npm) (GHSA-99rg-rwx3-5pjr)

## Resumen

The package ally-allowlist was found to contain malicious code.

The OpenSSF Package Analysis project identified 'ally-allowlist' @ 99.99.99 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `ally-allowlist` (npm), versiones afectadas: = 99.99.99
- `ally-allowlist` (npm), versiones afectadas: = 100.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T23:15:23Z
- Fuente: https://github.com/advisories/GHSA-99rg-rwx3-5pjr

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `ally-allowlist`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
