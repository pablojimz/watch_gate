# Aviso: Malicious code in reqcrypts (PyPI) (GHSA-p5hw-cgm2-4cp2)

## Resumen

The package contains a hidden backdoor. The promised functionality is an HTTP request library with some additional functions. On every usage, code secretly checks for the presence of specific fields in the response, and if they are found, their content is secretly executed.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-reqcrypt

Reasons (based on the campaign):

 - backdoor

## Paquetes afectados

- `reqcrypts` (pip), versiones afectadas: = 0.1.0
- `reqcrypts` (pip), versiones afectadas: = 0.1.1
- `reqcrypts` (pip), versiones afectadas: = 0.1.2
- `reqcrypts` (pip), versiones afectadas: = 0.1.3

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-21T03:31:24Z
- Fuente: https://github.com/advisories/GHSA-p5hw-cgm2-4cp2

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `reqcrypts`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
