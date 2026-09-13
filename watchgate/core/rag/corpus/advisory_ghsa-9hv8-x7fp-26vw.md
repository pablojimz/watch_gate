# Aviso: Malicious code in pymaas (PyPI) (GHSA-9hv8-x7fp-26vw)

## Resumen

During import, the package exfiltrates environment variables.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-09-amirgo4496

Reasons (based on the campaign):

 - exfiltration-env-variables

 - dependency-confusion

 - The package contains code to exfiltrate basic data from the system, like IP or username. It has a limited risk.

## Paquetes afectados

- `pymaas` (pip), versiones afectadas: = 99.99.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T18:31:11Z
- Fuente: https://github.com/advisories/GHSA-9hv8-x7fp-26vw

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `pymaas`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
