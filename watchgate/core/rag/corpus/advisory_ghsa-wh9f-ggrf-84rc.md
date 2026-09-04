# Aviso: Malicious code in damp_spoonbill_coral-60 (npm) (GHSA-wh9f-ggrf-84rc)

## Resumen

This package appears to be part of the tea.xyz token reward campaign that flooded npm. These packages typically contain autopublish scripts (auto.js, autopublish.js, autopublish2.js, autopublish3.js) designed to automatically generate and publish derivative packages with randomized names to inflate developer reputation scores for tea protocol token rewards. The malicious payload modifies package.json to remove private flags, changes version numbers, generates random Indonesian-themed package names (some variants are also in English), and continuously republishes variants to pollute the npm registry.

## Paquetes afectados

- `damp_spoonbill_coral-60` (npm), versiones afectadas: > 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T07:17:55Z
- Fuente: https://github.com/advisories/GHSA-wh9f-ggrf-84rc

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `damp_spoonbill_coral-60`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
