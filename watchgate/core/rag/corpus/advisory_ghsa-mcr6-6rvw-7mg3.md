# Aviso: Malicious code in astlsi (PyPI) (GHSA-mcr6-6rvw-7mg3)

## Resumen

The provided functionality hides code that exfiltrates files to a remote location.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-09-asti

Reasons (based on the campaign):

 - files-exfiltration

 - action-hidden-in-lib-usage

 - target:android

## Paquetes afectados

- `astlsi` (pip), versiones afectadas: = 0.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T12:31:01Z
- Fuente: https://github.com/advisories/GHSA-mcr6-6rvw-7mg3

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `astlsi`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
