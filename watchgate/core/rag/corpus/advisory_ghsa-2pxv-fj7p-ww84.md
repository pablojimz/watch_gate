# Aviso: Malicious code in dandelion-dune-cli341-project (npm) (GHSA-2pxv-fj7p-ww84)

## Resumen

The package dandelion-dune-cli341-project was found to contain malicious code.

## Paquetes afectados

- `dandelion-dune-cli341-project` (npm), versiones afectadas: > 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T07:17:55Z
- Fuente: https://github.com/advisories/GHSA-2pxv-fj7p-ww84

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `dandelion-dune-cli341-project`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
