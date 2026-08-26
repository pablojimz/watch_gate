# Aviso: Malicious code in requests-crypt (PyPI) (GHSA-cf52-hr54-m53p)

## Resumen

The package contains a hidden backdoor. The promised functionality is an HTTP request library with some additional functions. On every usage, code secretly checks for the presence of specific fields in the response, and if they are found, their content is secretly executed.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-reqcrypt

Reasons (based on the campaign):

 - backdoor

## Paquetes afectados

- `requests-crypt` (pip), versiones afectadas: = 0.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-21T12:30:34Z
- Fuente: https://github.com/advisories/GHSA-cf52-hr54-m53p

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `requests-crypt`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
