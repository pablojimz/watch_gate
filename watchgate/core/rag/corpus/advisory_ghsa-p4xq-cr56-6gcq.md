# Aviso: Malicious code in dandelion-cliff-atc189-project (npm) (GHSA-p4xq-cr56-6gcq)

## Resumen

The package dandelion-cliff-atc189-project was found to contain malicious code.

## Paquetes afectados

- `dandelion-cliff-atc189-project` (npm), versiones afectadas: > 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T07:17:55Z
- Fuente: https://github.com/advisories/GHSA-p4xq-cr56-6gcq

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `dandelion-cliff-atc189-project`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
