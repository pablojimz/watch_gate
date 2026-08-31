# Aviso: Malicious code in sap-quarterly-report (PyPI) (GHSA-3g4v-hc5w-c37x)

## Resumen

During import, the package collects sensitive information and exfiltrates it using DNS queries.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-ekx-report-utils

Reasons (based on the campaign):

 - targetted-attack

 - exfiltration-generic

 - exfiltration-credentials

## Paquetes afectados

- `sap-quarterly-report` (pip), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-27T15:30:29Z
- Fuente: https://github.com/advisories/GHSA-3g4v-hc5w-c37x

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `sap-quarterly-report`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
