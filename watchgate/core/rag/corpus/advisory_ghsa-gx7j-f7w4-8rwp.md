# Aviso: Malicious code in msrcpoc (PyPI) (GHSA-gx7j-f7w4-8rwp)

## Resumen

The OpenSSF Package Analysis project identified 'msrcpoc' @ 99.1.9 (pypi) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `msrcpoc` (pip), versiones afectadas: = 99.1.9

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T03:32:12Z
- Fuente: https://github.com/advisories/GHSA-gx7j-f7w4-8rwp

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `msrcpoc`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
