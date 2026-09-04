# Aviso: Malicious code in fuels-versions (npm) (GHSA-cxcx-864c-x6vp)

## Resumen

The package 'fuels-versions' was identified as containing malicious obfuscated code.

## Paquetes afectados

- `fuels-versions` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-01T06:33:01Z
- Fuente: https://github.com/advisories/GHSA-cxcx-864c-x6vp

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `fuels-versions`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
