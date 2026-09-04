# Aviso: Malicious code in dandelion-brook-wuk348-project (npm) (GHSA-5j95-p237-g537)

## Resumen

The package dandelion-brook-wuk348-project was found to contain malicious code.

## Paquetes afectados

- `dandelion-brook-wuk348-project` (npm), versiones afectadas: > 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T07:17:55Z
- Fuente: https://github.com/advisories/GHSA-5j95-p237-g537

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `dandelion-brook-wuk348-project`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
