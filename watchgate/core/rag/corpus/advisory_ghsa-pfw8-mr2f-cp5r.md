# Aviso: Malicious code in danasah (npm) (GHSA-pfw8-mr2f-cp5r)

## Resumen

The package danasah was found to contain malicious code.

## Paquetes afectados

- `danasah` (npm), versiones afectadas: > 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T07:17:55Z
- Fuente: https://github.com/advisories/GHSA-pfw8-mr2f-cp5r

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `danasah`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
