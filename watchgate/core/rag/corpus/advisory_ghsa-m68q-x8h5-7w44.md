# Aviso: Malicious code in dandelion-coral-rpv024-project (npm) (GHSA-m68q-x8h5-7w44)

## Resumen

The package dandelion-coral-rpv024-project was found to contain malicious code.

## Paquetes afectados

- `dandelion-coral-rpv024-project` (npm), versiones afectadas: > 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T07:17:55Z
- Fuente: https://github.com/advisories/GHSA-m68q-x8h5-7w44

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `dandelion-coral-rpv024-project`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
