# Aviso: Malicious code in rc4-secure (PyPI) (GHSA-q3mh-hmf4-7c8m)

## Resumen

Package silently installs a remote executable in a way that is intentionally hidden from the user. During analysis, the code was downloading a legitimate software unrelated to provided functionality, suggesting it is a research-like demonstration.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-rc4-secure

Reasons (based on the campaign):

 - Downloads and executes a remote executable.

 - modify-system-without-consent

 - action-hidden-in-lib-usage

## Paquetes afectados

- `rc4-secure` (pip), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-19T21:30:25Z
- Fuente: https://github.com/advisories/GHSA-q3mh-hmf4-7c8m

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `rc4-secure`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
