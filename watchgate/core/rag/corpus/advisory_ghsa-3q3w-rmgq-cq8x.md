# Aviso: Malicious code in yaml-report-formatter (PyPI) (GHSA-3q3w-rmgq-cq8x)

## Resumen

During import, the package collects sensitive information and exfiltrates it using DNS queries.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-ekx-report-utils

Reasons (based on the campaign):

 - targetted-attack

 - exfiltration-generic

 - exfiltration-credentials

## Paquetes afectados

- `yaml-report-formatter` (pip), versiones afectadas: = 0.1.0
- `yaml-report-formatter` (pip), versiones afectadas: = 0.2.0
- `yaml-report-formatter` (pip), versiones afectadas: = 0.3.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-28T12:30:30Z
- Fuente: https://github.com/advisories/GHSA-3q3w-rmgq-cq8x

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `yaml-report-formatter`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
