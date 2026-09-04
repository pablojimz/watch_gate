# Aviso: Malicious code in dandelion-giraffe-mpa122-project (npm) (GHSA-f227-2985-97vw)

## Resumen

The package dandelion-giraffe-mpa122-project was found to contain malicious code.

## Paquetes afectados

- `dandelion-giraffe-mpa122-project` (npm), versiones afectadas: > 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T07:17:55Z
- Fuente: https://github.com/advisories/GHSA-f227-2985-97vw

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `dandelion-giraffe-mpa122-project`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
