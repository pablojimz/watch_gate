# Aviso: Malicious code in npx-oob-package (npm) (GHSA-2gqg-4mch-fmq5)

## Resumen

The OpenSSF Package Analysis project identified 'npx-oob-package' @ 1.0.2 (npm) as malicious.

It is considered malicious because:

- The package communicates with a domain associated with malicious activity.

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `npx-oob-package` (npm), versiones afectadas: = 1.0.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T00:30:26Z
- Fuente: https://github.com/advisories/GHSA-2gqg-4mch-fmq5

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `npx-oob-package`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
