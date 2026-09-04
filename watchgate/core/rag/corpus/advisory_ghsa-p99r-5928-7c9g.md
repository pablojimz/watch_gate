# Aviso: Malicious code in dandelion-amber-owt940-project (npm) (GHSA-p99r-5928-7c9g)

## Resumen

The package dandelion-amber-owt940-project was found to contain malicious code.

## Paquetes afectados

- `dandelion-amber-owt940-project` (npm), versiones afectadas: > 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T07:17:55Z
- Fuente: https://github.com/advisories/GHSA-p99r-5928-7c9g

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `dandelion-amber-owt940-project`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
