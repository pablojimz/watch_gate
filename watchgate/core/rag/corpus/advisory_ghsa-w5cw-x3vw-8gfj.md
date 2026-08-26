# Aviso: Malicious code in @immuta/pxl-components (npm) (GHSA-w5cw-x3vw-8gfj)

## Resumen

Malicious package due to data exfiltration, arbitrary command execution, and suspicious install scripts targeting dependency confusion.## Source: amazon-inspector (03d86f67d7f931d0f720838a4bda33d56a54a5502b29ebe3e1094a984041b7a2)
The package @immuta/pxl-components was found to contain malicious code.

## Paquetes afectados

- `@immuta/pxl-components` (npm), versiones afectadas: = 99.99.1
- `@immuta/pxl-components` (npm), versiones afectadas: = 99.99.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T06:31:24Z
- Fuente: https://github.com/advisories/GHSA-w5cw-x3vw-8gfj

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `@immuta/pxl-components`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
