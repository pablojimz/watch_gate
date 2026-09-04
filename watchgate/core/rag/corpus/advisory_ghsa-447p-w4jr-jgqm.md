# Aviso: Malicious code in alloydemo (npm) (GHSA-447p-w4jr-jgqm)

## Resumen

The package alloydemo was found to contain malicious code.

## Paquetes afectados

- `alloydemo` (npm), versiones afectadas: > 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T23:15:23Z
- Fuente: https://github.com/advisories/GHSA-447p-w4jr-jgqm

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `alloydemo`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
