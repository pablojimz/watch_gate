# Aviso: Malicious code in asti (PyPI) (GHSA-wjq4-hhv5-qv6v)

## Resumen

The provided functionality hides code that exfiltrates files to a remote location.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-09-asti

Reasons (based on the campaign):

 - files-exfiltration

 - action-hidden-in-lib-usage

 - target:android

## Paquetes afectados

- `asti` (pip), versiones afectadas: = 0.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-03T21:31:14Z
- Fuente: https://github.com/advisories/GHSA-wjq4-hhv5-qv6v

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `asti`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
