# Aviso: Malicious code in ekx-report-utils (PyPI) (GHSA-77v5-hfrm-j4h4)

## Resumen

During import, the package collects sensitive information and exfiltrates it using DNS queries.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-ekx-report-utils

Reasons (based on the campaign):

 - targetted-attack

 - exfiltration-generic

 - exfiltration-credentials

## Paquetes afectados

- `ekx-report-utils` (pip), versiones afectadas: = 0.1.0
- `ekx-report-utils` (pip), versiones afectadas: = 0.2.0
- `ekx-report-utils` (pip), versiones afectadas: = 0.3.0
- `ekx-report-utils` (pip), versiones afectadas: = 0.4.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-27T15:30:29Z
- Fuente: https://github.com/advisories/GHSA-77v5-hfrm-j4h4

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `ekx-report-utils`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
